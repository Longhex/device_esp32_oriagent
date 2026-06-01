package xiaozhi.modules.device.controller;

import org.apache.commons.lang3.StringUtils;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import cn.hutool.http.ContentType;
import cn.hutool.http.Header;
import cn.hutool.http.HttpRequest;
import cn.hutool.json.JSONUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.sys.service.SysParamsService;

/**
 * Mặt phẳng giám sát/quản lý thiết bị qua MQTT (EMQX) — proxy sang service device-monitor.
 *
 * Độc lập với luồng audio xiaozhi. device-monitor là consumer Python expose HTTP API;
 * controller này bọc nó dưới xác thực JWT/Shiro của console để web/app dùng chung.
 *
 * Tham số địa chỉ: server.device_monitor_api (mặc định http://device-monitor:8090).
 */
@Tag(name = "设备监控管理")
@Slf4j
@RestController
@RequestMapping("/agentDeviceMonitor")
@RequiredArgsConstructor
public class DeviceMonitorController {

    private final SysParamsService sysParamsService;

    private static final String DEFAULT_BASE = "http://device-monitor:8090";
    private static final int TIMEOUT = 8000;

    private String base() {
        String url = sysParamsService.getValue("server.device_monitor_api", true);
        if (StringUtils.isBlank(url) || "null".equals(url)) {
            return DEFAULT_BASE;
        }
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }

    private Result<Object> proxyGet(String path) {
        try {
            String body = HttpRequest.get(base() + path).timeout(TIMEOUT).execute().body();
            return new Result<Object>().ok(JSONUtil.parse(body));
        } catch (Exception e) {
            log.error("device-monitor GET {} failed: {}", path, e.getMessage());
            return new Result<Object>().error("Không kết nối được device-monitor: " + e.getMessage());
        }
    }

    private Result<Object> proxySend(String method, String path, String requestBody) {
        try {
            HttpRequest req = "DELETE".equals(method) ? HttpRequest.delete(base() + path)
                    : HttpRequest.post(base() + path);
            req.header(Header.CONTENT_TYPE, ContentType.JSON.getValue()).timeout(TIMEOUT);
            if (StringUtils.isNotBlank(requestBody)) {
                req.body(requestBody);
            }
            String body = req.execute().body();
            return new Result<Object>().ok(StringUtils.isBlank(body) ? null : JSONUtil.parse(body));
        } catch (Exception e) {
            log.error("device-monitor {} {} failed: {}", method, path, e.getMessage());
            return new Result<Object>().error("Không kết nối được device-monitor: " + e.getMessage());
        }
    }

    // ---------- Giám sát ----------
    @GetMapping("/devices")
    @Operation(summary = "Danh sách thiết bị + trạng thái")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> listDevices() {
        return proxyGet("/devices");
    }

    @GetMapping("/devices/{serial}")
    @Operation(summary = "Chi tiết 1 thiết bị")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> getDevice(@PathVariable String serial) {
        return proxyGet("/devices/" + serial);
    }

    @PostMapping("/devices/{serial}/command")
    @Operation(summary = "Gửi lệnh điều khiển thiết bị")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> sendCommand(@PathVariable String serial, @RequestBody(required = false) String body) {
        return proxySend("POST", "/devices/" + serial + "/command", body);
    }

    // ---------- Quản lý Serial ----------
    @GetMapping("/serials")
    @Operation(summary = "Danh sách serial đã khai báo")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> listSerials() {
        return proxyGet("/serials");
    }

    @PostMapping("/serials")
    @Operation(summary = "Khai báo serial")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> declareSerial(@RequestBody String body) {
        return proxySend("POST", "/serials", body);
    }

    @PostMapping("/activate")
    @Operation(summary = "Kích hoạt serial (cấp MQTT credential)")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> activate(@RequestBody String body) {
        return proxySend("POST", "/activate", body);
    }

    @DeleteMapping("/serials/{serial}")
    @Operation(summary = "Gỡ thiết bị (unbind)")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> deleteSerial(@PathVariable String serial) {
        return proxySend("DELETE", "/serials/" + serial, null);
    }
}
