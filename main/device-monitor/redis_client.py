"""Helper khởi tạo Redis dùng chung. REDIS_HOST rỗng = tắt (trả None)."""
import common


def get_redis(logger=None):
    log = logger or (lambda m: None)
    if not common.REDIS_HOST:
        log("[redis] TẮT (chưa set REDIS_HOST) -> in-memory")
        return None
    try:
        import redis
    except ImportError:
        log("[redis] redis-py chưa cài -> in-memory")
        return None
    try:
        c = redis.Redis(
            host=common.REDIS_HOST, port=common.REDIS_PORT, password=common.REDIS_PASSWORD,
            socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
        c.ping()
        log(f"[redis] OK {common.REDIS_HOST}:{common.REDIS_PORT}")
        return c
    except Exception as e:
        log(f"[redis] không kết nối được ({e}) -> in-memory")
        return None
