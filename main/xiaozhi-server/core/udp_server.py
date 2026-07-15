import asyncio
import secrets
import struct
import time
from config.logger import setup_logging, bind_log_context
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

TAG = "udp_server"
HYBRID_EOS_MARKER = "__hybrid_udp_eos__"
HK_UDP_HEADER_SIZE = 16
HK_UDP_AUDIO_TYPE = 0x01


def aes_ctr_crypt(key, counter, payload):
    """Encrypt/decrypt one HK UDP payload using its transmitted header as CTR."""
    if len(key) != 16 or len(counter) != HK_UDP_HEADER_SIZE:
        raise ValueError("HK UDP AES-CTR requires a 16-byte key and counter")
    cipher = Cipher(algorithms.AES(key), modes.CTR(counter))
    cryptor = cipher.encryptor()
    return cryptor.update(payload) + cryptor.finalize()


def build_hk_udp_packet(key, ssrc, timestamp, sequence, payload, flags=0):
    if len(payload) > 0xFFFF:
        raise ValueError("HK UDP payload is too large")
    header = struct.pack(
        "!BBHIII",
        HK_UDP_AUDIO_TYPE,
        flags & 0xFF,
        len(payload),
        ssrc & 0xFFFFFFFF,
        timestamp & 0xFFFFFFFF,
        sequence & 0xFFFFFFFF,
    )
    return header + aes_ctr_crypt(key, header, payload)


def parse_hk_udp_packet(key, data, expected_ssrc=None):
    if len(data) < HK_UDP_HEADER_SIZE:
        raise ValueError("packet_too_short")
    header = data[:HK_UDP_HEADER_SIZE]
    packet_type, flags, payload_len, ssrc, timestamp, sequence = struct.unpack(
        "!BBHIII", header
    )
    if packet_type != HK_UDP_AUDIO_TYPE:
        raise ValueError("invalid_packet_type")
    if expected_ssrc is not None and ssrc != expected_ssrc:
        raise ValueError("invalid_ssrc")
    encrypted = data[HK_UDP_HEADER_SIZE:]
    if payload_len != len(encrypted):
        raise ValueError("invalid_payload_length")
    payload = aes_ctr_crypt(key, header, encrypted)
    return flags, ssrc, timestamp, sequence, payload


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


class HkEncryptedUdpSession:
    """HK firmware UDP/AES-CTR media session.

    The device copies the server-provided 16-byte nonce template into every
    uplink packet and overwrites payload length, timestamp and sequence. The
    four-byte SSRC remains stable, so it is also the session routing key.
    """

    def __init__(
        self,
        device_id,
        session_id,
        asr_audio_queue,
        output_sample_rate=24000,
        frame_duration=60,
        key=None,
        client_ssrc=None,
        logger=None,
    ):
        self.device_id = device_id
        self.session_id = session_id
        self.asr_audio_queue = asr_audio_queue
        self.output_sample_rate = int(output_sample_rate)
        self.frame_duration = int(frame_duration)
        self.key = key or secrets.token_bytes(16)
        self.client_ssrc = (
            int(client_ssrc) & 0xFFFFFFFF
            if client_ssrc is not None
            else int.from_bytes(secrets.token_bytes(4), "big")
        )
        # Separate the CTR domains in each direction even if timestamps and
        # sequences happen to coincide.
        self.server_ssrc = self.client_ssrc ^ 0x80000000
        self.nonce_template = struct.pack(
            "!BBHIII", HK_UDP_AUDIO_TYPE, 0, 0, self.client_ssrc, 0, 0
        )
        self.client_addr = None
        self.transport = None
        self.last_active_time = time.time()
        self.last_rx_sequence = 0
        self.tx_sequence = 0
        self.tx_timestamp = 0
        self.closed = False
        self.rx_packet_count = 0
        self.rx_bytes_total = 0
        self.logger = bind_log_context(
            logger or setup_logging(),
            transport="HK_MQTT_UDP",
            phase="MEDIA",
            device_id=device_id,
            session_id=session_id,
        )

    def hello_udp_config(self, public_host, port):
        return {
            "server": public_host,
            "port": int(port),
            "key": self.key.hex(),
            "nonce": self.nonce_template.hex(),
        }

    def handle_datagram(self, data, addr):
        flags, _, timestamp, sequence, payload = parse_hk_udp_packet(
            self.key, data, expected_ssrc=self.client_ssrc
        )
        if sequence <= self.last_rx_sequence:
            self.logger.bind(tag=TAG).warning(
                f"[HK-UDP] dropped replay/out-of-order sequence={sequence} "
                f"last={self.last_rx_sequence}"
            )
            return False

        self.client_addr = addr
        self.last_active_time = time.time()
        self.last_rx_sequence = sequence
        self.rx_packet_count += 1
        self.rx_bytes_total += len(payload)
        if flags == 0xFF:
            self.asr_audio_queue.put(
                {
                    "type": HYBRID_EOS_MARKER,
                    "session_id": self.session_id,
                    "device_id": self.device_id,
                    "received_at": self.last_active_time,
                }
            )
        else:
            self.asr_audio_queue.put(payload)
        if self.rx_packet_count == 1 or self.rx_packet_count % 25 == 0:
            self.logger.bind(tag=TAG).info(
                f"[HK-UDP] uplink packets={self.rx_packet_count} "
                f"bytes_total={self.rx_bytes_total} from={addr} timestamp={timestamp}"
            )
        return True

    def send_audio(self, data, payload_type=HK_UDP_AUDIO_TYPE):
        if not self.transport or not self.client_addr or self.closed:
            return False
        self.tx_sequence += 1
        samples_per_frame = max(
            1, int(self.output_sample_rate * self.frame_duration / 1000)
        )
        self.tx_timestamp = (self.tx_timestamp + samples_per_frame) & 0xFFFFFFFF
        flags = 0 if payload_type == HK_UDP_AUDIO_TYPE else payload_type
        packet = build_hk_udp_packet(
            self.key,
            self.server_ssrc,
            self.tx_timestamp,
            self.tx_sequence,
            data,
            flags=flags,
        )
        self.transport.sendto(packet, self.client_addr)
        return True

    def close(self, reason="session_closed"):
        self.closed = True
        self.logger.bind(tag=TAG).info(
            f"[HK-UDP] Session {self.session_id} closed reason={reason}"
        )

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
            if data and data[0] == HK_UDP_AUDIO_TYPE and len(data) >= HK_UDP_HEADER_SIZE:
                ssrc = struct.unpack("!I", data[4:8])[0]
                session = self.manager.get_hk_session_by_ssrc(ssrc)
                if not session:
                    self.logger.bind(tag=TAG).warning(
                        f"[HK-UDP] unknown ssrc=0x{ssrc:08X} from={addr}"
                    )
                    return
                if not session.transport:
                    session.transport = self.transport
                session.handle_datagram(data, addr)
                return

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
        self.hk_sessions_by_ssrc = {}
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

    def create_hk_session(
        self,
        device_id,
        session_id,
        asr_audio_queue,
        output_sample_rate=24000,
        frame_duration=60,
        key=None,
        client_ssrc=None,
    ):
        while True:
            session = HkEncryptedUdpSession(
                device_id,
                session_id,
                asr_audio_queue,
                output_sample_rate=output_sample_rate,
                frame_duration=frame_duration,
                key=key,
                client_ssrc=client_ssrc,
                logger=self.logger,
            )
            if session.client_ssrc not in self.hk_sessions_by_ssrc:
                break
            if client_ssrc is not None:
                raise ValueError("HK UDP SSRC is already active")
        session.transport = self.transport
        self.sessions[session_id] = session
        self.hk_sessions_by_ssrc[session.client_ssrc] = session
        self.logger.bind(tag=TAG).info(
            f"[HK-UDP] Created session device={device_id} session={session_id} "
            f"ssrc=0x{session.client_ssrc:08X}"
        )
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def get_hk_session_by_ssrc(self, ssrc):
        return self.hk_sessions_by_ssrc.get(ssrc)

    def close_session(self, session_id, reason="session_closed"):
        session = self.sessions.pop(session_id, None)
        if session:
            if isinstance(session, HkEncryptedUdpSession):
                self.hk_sessions_by_ssrc.pop(session.client_ssrc, None)
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
        self.hk_sessions_by_ssrc.clear()

# Global singleton
udp_manager = UdpServerManager()
