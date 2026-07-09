from typing import Dict, Any
from config.logger import setup_logging
from core.utils import tts, llm, intent, memory, vad, asr

TAG = __name__
logger = setup_logging()


def _resolve_provider_selection(config: Dict[str, Any], module_name: str):
    selected_key = config.get("selected_module", {}).get(module_name)
    module_configs = config.get(module_name, {})
    provider_config = module_configs.get(selected_key, {}) if selected_key else {}
    provider_type = provider_config.get("type", selected_key)
    return selected_key, provider_type, provider_config


def _log_provider_selection(
    logger,
    module_name: str,
    selected_key: str,
    provider_type: str,
    provider_instance,
    source: str,
):
    provider_class = (
        f"{provider_instance.__class__.__module__}.{provider_instance.__class__.__name__}"
        if provider_instance is not None
        else "uninitialized"
    )
    logger.bind(tag=TAG).info(
        "[PROVIDER-SELECT] {}_provider key={} type={} class={} source={}",
        module_name.lower(),
        selected_key or "unset",
        provider_type or "unset",
        provider_class,
        source,
    )


def initialize_modules(
    logger,
    config: Dict[str, Any],
    init_vad=False,
    init_asr=False,
    init_llm=False,
    init_tts=False,
    init_memory=False,
    init_intent=False,
) -> Dict[str, Any]:
    """
    初始化所有模块组件

    Args:
        config: 配置字典

    Returns:
        Dict[str, Any]: 包含所有初始化后的模块的字典
    """
    modules = {}

    # 初始化TTS模块
    if init_tts:
        select_tts_module = config["selected_module"]["TTS"]
        modules["tts"] = initialize_tts(config)
        logger.bind(tag=TAG).info(f"初始化组件: tts成功 {select_tts_module}")

    # 初始化LLM模块
    if init_llm:
        select_llm_module, llm_type, provider_config = _resolve_provider_selection(
            config, "LLM"
        )
        modules["llm"] = llm.create_instance(
            llm_type,
            provider_config,
        )
        _log_provider_selection(
            logger,
            "LLM",
            select_llm_module,
            llm_type,
            modules["llm"],
            "selected_module_config",
        )
        logger.bind(tag=TAG).info(f"初始化组件: llm成功 {select_llm_module}")

    # 初始化Intent模块
    if init_intent:
        select_intent_module = config["selected_module"]["Intent"]
        intent_type = (
            select_intent_module
            if "type" not in config["Intent"][select_intent_module]
            else config["Intent"][select_intent_module]["type"]
        )
        modules["intent"] = intent.create_instance(
            intent_type,
            config["Intent"][select_intent_module],
        )
        logger.bind(tag=TAG).info(f"Component initialized: Intent successful {select_intent_module}")

    # Initialize Memory module
    if init_memory:
        select_memory_module = config["selected_module"]["Memory"]
        memory_type = (
            select_memory_module
            if "type" not in config["Memory"][select_memory_module]
            else config["Memory"][select_memory_module]["type"]
        )
        modules["memory"] = memory.create_instance(
            memory_type,
            config["Memory"][select_memory_module],
            config.get("summaryMemory", None),
        )
        logger.bind(tag=TAG).info(f"Component initialized: Memory successful {select_memory_module}")

    # Initialize VAD module
    if init_vad:
        select_vad_module = config["selected_module"]["VAD"]
        vad_type = (
            select_vad_module
            if "type" not in config["VAD"][select_vad_module]
            else config["VAD"][select_vad_module]["type"]
        )
        modules["vad"] = vad.create_instance(
            vad_type,
            config["VAD"][select_vad_module],
        )
        logger.bind(tag=TAG).info(f"Component initialized: VAD successful {select_vad_module}")

    # Initialize ASR module
    if init_asr:
        select_asr_module = config["selected_module"]["ASR"]
        modules["asr"] = initialize_asr(config)
        logger.bind(tag=TAG).info(f"Component initialized: ASR successful {select_asr_module}")
    return modules


def initialize_tts(config):
    select_tts_module, tts_type, provider_config = _resolve_provider_selection(
        config, "TTS"
    )
    new_tts = tts.create_instance(
        tts_type,
        provider_config,
        str(config.get("delete_audio", True)).lower() in ("true", "1", "yes"),
    )
    _log_provider_selection(
        logger,
        "TTS",
        select_tts_module,
        tts_type,
        new_tts,
        "selected_module_config",
    )
    return new_tts


def initialize_asr(config):
    select_asr_module, asr_type, provider_config = _resolve_provider_selection(
        config, "ASR"
    )
    new_asr = asr.create_instance(
        asr_type,
        provider_config,
        str(config.get("delete_audio", True)).lower() in ("true", "1", "yes"),
    )
    _log_provider_selection(
        logger,
        "ASR",
        select_asr_module,
        asr_type,
        new_asr,
        "selected_module_config",
    )
    logger.bind(tag=TAG).info("ASR module initialization complete")
    return new_asr


def initialize_voiceprint(asr_instance, config):
    """Initialize voiceprint recognition function"""
    voiceprint_config = config.get("voiceprint")
    if not voiceprint_config:
        return False  

    # 应用配置
    if not voiceprint_config.get("url") or not voiceprint_config.get("speakers"):
        logger.bind(tag=TAG).warning("声纹识别配置不完整")
        return False
        
    try:
        asr_instance.init_voiceprint(voiceprint_config)
        logger.bind(tag=TAG).info("ASR模块声纹识别功能已动态启用")
        logger.bind(tag=TAG).info(f"配置说话人数量: {len(voiceprint_config['speakers'])}")
        return True
    except Exception as e:
        logger.bind(tag=TAG).error(f"动态初始化声纹识别功能失败: {str(e)}")
        return False
