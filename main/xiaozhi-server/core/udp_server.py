import asyncio
import struct
import time
from config.logger import setup_logging, bind_log_context

TAG = "udp_server"
HYBRID_EOS_MARKER = "__hybrid_udp_eos__"


def build_udp_header(session_id, seq_num, flags, reserved=0):
    if not isinstance(session_id, str):
        raise ValueError("session_id must be a string")
    if not session_id or len(session_id) > 8:
        raise ValueError("session_id must contain 1..8 ASCII characters")
    try:
        session_id_bytes = session_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("session_id must be ASCII") from exc

    return struct.pack(
        "!8s H B B",
        session_id_bytes.ljust(8, b"\x00"),
        seq_num & 0xFFFF,
        flags & 0xFF,
        reserved & 0xFF,
    )


def parse_udp_packet(data):
    if len(data) < 12:
        raise ValueError("packet_too_short")

    session_id_bytes, seq_num, flags, reserved = struct.unpack("!8s H B B", data[:12])
    try:
        session_id = session_id_bytes.decode("ascii").rstrip("\x00")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_session_id") from exc

    if not session_id:
        raise ValueError("invalid_session_id")

    payload = data[12:]
    return session_id, seq_num, flags, reserved, payload

class UdpMediaSession:
    """Represents a single device's media stream session"""
    def __init__(self, device_id, session_id, asr_audio_queue, logger=None):
        self.device_id = device_id
        self.session_id = session_id  # 8-byte ASCII string
        self.asr_audio_queue = asr_audio_queue
        self.logger = bind_log_context(logger or setup_logging(), transport="UDP", phase="MEDIA", device_id=device_id, session_id=session_id)
        
        self.client_addr = None
        self.last_active_time = time.time()
        self.last_seq_num = -1
        self.tx_seq_num = 0
        self.closed = False
        self.rx_packet_count = 0
        self.rx_bytes_total = 0
        
        # We need a reference to the global multiplexer transport to send data back
        self.transport = None

    def handle_audio_packet(self, seq_num, flags, payload, addr):
        self.last_active_time = time.time()
        
        # Update client address if changed (e.g. NAT rebinding)
        if self.client_addr != addr:
            self.client_addr = addr
            self.logger.bind(tag=TAG).info(f"[UDP] Session {self.session_id} bound to address {addr}")

        # Handle End-of-Stream flag (0xFF)
        if flags == 0xFF:
            self.logger.bind(tag=TAG).info(f"[UDP] Session {self.session_id} received End-of-Stream flag.")
            if self.asr_audio_queue:
                self.asr_audio_queue.put(
                    {
                        "type": HYBRID_EOS_MARKER,
                        "session_id": self.session_id,
                        "device_id": self.device_id,
                        "received_at": self.last_active_time,
                    }
                )
        else:
            # Check for out-of-order or duplicate packets
            # UDP SeqNum is 16-bit, so it wraps around at 65535
            if self.last_seq_num != -1:
                # Basic wrap-around check: if difference is huge, it probably wrapped
                diff = (seq_num - self.last_seq_num) & 0xFFFF
                if diff > 32768: # Packet is older than last received (out of order)
                    self.logger.bind(tag=TAG).debug(f"Dropped out-of-order packet: {seq_num} <= {self.last_seq_num}")
                    return

            self.last_seq_num = seq_num
            
            if self.asr_audio_queue:
                self.asr_audio_queue.put(payload)
                self.rx_packet_count += 1
                self.rx_bytes_total += len(payload)
                if self.rx_packet_count == 1 or self.rx_packet_count % 25 == 0:
                    queue_size = None
                    try:
                        queue_size = self.asr_audio_queue.qsize()
                    except (AttributeError, NotImplementedError):
                        queue_size = None

                    log_msg = (
                        f"[HYBRID-AUDIO] udp_enqueue device={self.device_id} "
                        f"session={self.session_id} packets={self.rx_packet_count} "
                        f"bytes_total={self.rx_bytes_total}"
                    )
                    if queue_size is not None:
                        log_msg += f" queue_size={queue_size}"
                    else:
                        log_msg += " queue_size=unavailable"
                    self.logger.bind(tag=TAG).info(log_msg)

    def send_audio(self, data, payload_type=0x01):
        """
        Send audio back to the client.
        We must wrap it in the same 12-byte header so ESP32 knows it's from us.
        """
        if self.transport and self.client_addr and not self.closed:
            header = build_udp_header(self.session_id, self.tx_seq_num, payload_type, 0)
            self.transport.sendto(header + data, self.client_addr)
            self.tx_seq_num = (self.tx_seq_num + 1) & 0xFFFF
            return True
        return False

    def close(self, reason="session_closed"):
        self.closed = True
        self.logger.bind(tag=TAG).info(f"[UDP] Session {self.session_id} marked as closed reason={reason}")

class UdpMultiplexerProtocol(asyncio.DatagramProtocol):
    """Single UDP port listener that multiplexes all incoming packets to their respective sessions"""
    def __init__(self, manager):
        self.manager = manager
        self.logger = bind_log_context(setup_logging(), transport="UDP", phase="MEDIA")
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        port = transport.get_extra_info('sockname')[1]
        self.manager.transport = transport
        self.logger.bind(tag=TAG).info(f"[UDP Multiplexer] Listening on port {port}")

    def datagram_received(self, data, addr):
        try:
            session_id, seq_num, flags, reserved, payload = parse_udp_packet(data)
            session = self.manager.get_session(session_id)
            if session:
                # Give session a reference to transport so it can reply
                if not session.transport:
                    session.transport = self.transport
                session.handle_audio_packet(seq_num, flags, payload, addr)
            else:
                self.logger.bind(tag=TAG).info(
                    f"[UDP] Unknown session_id={session_id} from={addr} seq={seq_num} flags=0x{flags:02X} payload={len(payload)}"
                )

        except ValueError as e:
            self.logger.bind(tag=TAG).debug(f"Rejected UDP packet from {addr}: {e}")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Error parsing UDP packet from {addr}: {e}")

class UdpServerManager:
    def __init__(self):
        self.logger = bind_log_context(setup_logging(), transport="UDP", phase="MEDIA")
        self.sessions = {} # session_id -> UdpMediaSession
        self.transport = None
        self.port = 5000 # Default port

    async def start_server(self, port=5000):
        self.port = port
        loop = asyncio.get_running_loop()
        
        self.logger.bind(tag=TAG).info(f"[UDP Manager] Starting multiplexer on port {self.port}...")
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UdpMultiplexerProtocol(self),
            local_addr=('0.0.0.0', self.port)
        )
        self.transport = transport
        return self.port

    def create_session(self, device_id, session_id, asr_audio_queue):
        """Create a new session context. Must have an 8-character ASCII session_id"""
        session = UdpMediaSession(device_id, session_id, asr_audio_queue, self.logger)
        self.sessions[session_id] = session
        self.logger.bind(tag=TAG).info(f"[UDP Manager] Created context for device {device_id} (session {session_id})")
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def close_session(self, session_id, reason="session_closed"):
        session = self.sessions.pop(session_id, None)
        if session:
            session.close(reason=reason)
            self.logger.bind(tag=TAG).info(
                f"[UDP Manager] Removed context device={session.device_id} session={session_id} reason={reason}"
            )

    async def stop_server(self):
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)

        if self.transport:
            self.transport.close()
            self.transport = None

# Global singleton
udp_manager = UdpServerManager()
