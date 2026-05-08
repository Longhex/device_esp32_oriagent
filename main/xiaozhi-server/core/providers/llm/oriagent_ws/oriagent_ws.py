import json
import httpx
from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()

class LLMProvider(LLMProviderBase):
    """
    Oriagent LLM Provider (REST API Streaming variant, Dify-based)
    Uses synchronous HTTP streaming to match the framework's sync generator interface.
    """
    is_dify_provider = True  # Flag to distinguish Dify-based providers

    def __init__(self, config):
        # Configure API URL (priority: api_url > url > base_url)
        self.api_url = config.get("api_url") or config.get("url") or config.get("base_url")
        self.api_key = config.get("api_key")
        self.model_name = config.get("model_name", "oriagent-default")
        self.session_conversation_map = {}  # Map session IDs to Oriagent conversation IDs

    def _mask_token(self, token):
        if not token or len(str(token)) < 10:
            return "***"
        s_token = str(token)
        return f"{s_token[:6]}...{s_token[-4:]}"

    def response(self, session_id, dialogue, **kwargs):
        """
        Synchronous streaming generator via HTTP REST SSE to match Oriagent/Dify schema.
        Must be a sync generator (not async) to be compatible with the framework.
        """
        if not self.api_url:
            yield "Error: Oriagent API URL is not configured."
            return

        # Extract the latest user query
        try:
            last_msg = next(m for m in reversed(dialogue) if m.get("role") == "user")
            query = last_msg.get("content", "")
        except StopIteration:
            query = "Hello"

        # Priority: explicit kwarg > internal map
        conversation_id = kwargs.get("conversation_id", "") or self.session_conversation_map.get(session_id, "")
        on_conversation_id = kwargs.get("on_conversation_id")

        # Target payload structure matching Oriagent REST requirements
        request_payload = {
            "inputs": {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": session_id,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        logger.bind(tag=TAG).info(
            f"Calling Oriagent API | URL: {self.api_url} | ConvID: {conversation_id or 'New'}"
        )

        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream("POST", self.api_url, headers=headers, json=request_payload) as r:
                    if r.status_code != 200:
                        error_body = r.read()
                        logger.bind(tag=TAG).error(f"Oriagent API Error (Status {r.status_code}): {error_body.decode()}")
                        yield f" [HTTP Error {r.status_code}: {error_body.decode()[:100]}] "
                        return

                    for line in r.iter_lines():
                        if line.startswith("data: "):
                            try:
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                    
                                event = json.loads(data_str)
                                event_type = event.get("event")
                                
                                # Enhanced Logging: Log all event types for observability
                                logger.bind(tag=TAG).debug(f"Oriagent SSE Event: {event_type}")

                                # Persist conversation_id for subsequent turns
                                if not conversation_id and event.get("conversation_id"):
                                    conversation_id = event.get("conversation_id")
                                    self.session_conversation_map[session_id] = conversation_id
                                    if callable(on_conversation_id):
                                        on_conversation_id(conversation_id)
                                
                                # EVENT WHITELIST: Only yield actual text content (message or agent_message)
                                # This blocks prompt leakage from agent_thought or other diagnostic events
                                if event_type in ["message", "agent_message"] and event.get("answer"):
                                    yield event["answer"]
                                # CATCH TOOL OUTPUT (Observation from agent_thought)
                                elif event_type == "agent_thought" and event.get("observation"):
                                    obs = event["observation"]
                                    try:
                                        # Parse and prettify JSON for log readability
                                        from core.utils.util import recursive_json_prettify
                                        parsed = json.loads(obs) if isinstance(obs, str) else obs
                                        pretty_obj = recursive_json_prettify(parsed)
                                        pretty_json = json.dumps(pretty_obj, indent=2, ensure_ascii=False)
                                        # Unescape for terminal rendering
                                        pretty_json = pretty_json.replace("\\n", "\n").replace('\\"', '"')
                                        logger.bind(tag=TAG).info(f"\n{'='*20} ORIAGENT TOOL OUTPUT {'='*20}\n{pretty_json}\n{'='*62}")
                                    except:
                                        logger.bind(tag=TAG).info(f"ORIAGENT TOOL RETURN: {obs}")
                                    
                                    # ULTIMATE FIX: Yield hardware commands without double-encoding
                                    is_hardware = False
                                    final_obs = obs
                                    if isinstance(obs, str):
                                        if '%' in obs or '"type": "mcp"' in obs:
                                            is_hardware = True
                                    elif isinstance(obs, dict):
                                        obs_json = json.dumps(obs, ensure_ascii=False)
                                        if '%' in obs_json or '"type": "mcp"' in obs_json:
                                            is_hardware = True
                                            final_obs = obs_json
                                            
                                    if is_hardware:
                                        logger.bind(tag=TAG).info(f"!!! CRITICAL ORIAGENT YIELD !!! -> {str(final_obs)[:100]}")
                                        yield final_obs
                                    else:
                                        logger.bind(tag=TAG).debug(f"Skipping internal tool observation")
                                elif event_type == "message_end":
                                    logger.bind(tag=TAG).debug(f"Oriagent message end. Total message tokens received.")
                                    break
                                elif event_type == "error":
                                    error_msg = event.get("message", "Unknown Oriagent error")
                                    logger.bind(tag=TAG).error(f"Oriagent API Internal Error: {error_msg}")
                                    yield f" [LLM Error: {error_msg}] "
                                    break
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.bind(tag=TAG).error(f"Failed to connect to Oriagent: {str(e)}")
            yield f" [System Error: Connection to Oriagent failed] "

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        """
        Wrapper for function-calling support. 
        Note: Specific Oriagent model configuration required for true function calling.
        """
        for token in self.response(session_id, dialogue, **kwargs):
            yield token, None
