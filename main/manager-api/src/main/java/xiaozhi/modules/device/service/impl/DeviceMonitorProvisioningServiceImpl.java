package xiaozhi.modules.device.service.impl;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import cn.hutool.http.ContentType;
import cn.hutool.http.Header;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.device.service.DeviceMonitorProvisioningService;
import xiaozhi.modules.sys.service.SysParamsService;

/**
 * Manager-side boundary for device-monitor provisioning.
 *
 * Device ownership/configuration stays in Manager API. device-monitor owns
 * its Redis serial registry and MQTT provisioning, so Manager API calls its
 * HTTP contract instead of writing Redis directly.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DeviceMonitorProvisioningServiceImpl implements DeviceMonitorProvisioningService {

    static final String DEVICE_MONITOR_API_PARAM = "server.device_monitor_api";
    static final String DEFAULT_BASE_URL = "http://device-monitor:8090";
    static final int TIMEOUT_MS = 8000;

    private final SysParamsService sysParamsService;

    @Override
    public void declareDevice(String serial, String batch) {
        if (StringUtils.isBlank(serial)) {
            throw new RenException("Không thể provisioning MQTT: MAC/serial trống");
        }

        JSONObject request = JSONUtil.createObj().set("serial", serial.trim());
        if (StringUtils.isNotBlank(batch)) {
            request.set("batch", batch.trim());
        }

        String url = baseUrl() + "/serials";
        try (HttpResponse response = HttpRequest.post(url)
                .header(Header.CONTENT_TYPE, ContentType.JSON.getValue())
                .body(request.toString())
                .timeout(TIMEOUT_MS)
                .execute()) {
            int status = response.getStatus();
            if (status != 200 && status != 201) {
                log.warn("device-monitor declare failed serial={} status={}", serial, status);
                throw new RenException("Không thể khai báo MQTT provisioning cho thiết bị (HTTP " + status + ")");
            }
            log.info("device-monitor serial declared serial={} status={}", serial, status);
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            log.error("device-monitor declare unavailable serial={}: {}", serial, e.getMessage());
            throw new RenException("Không kết nối được device-monitor để khai báo MQTT provisioning");
        }
    }

    private String baseUrl() {
        String configured = sysParamsService.getValue(DEVICE_MONITOR_API_PARAM, true);
        String baseUrl = StringUtils.isBlank(configured) || "null".equalsIgnoreCase(configured)
                ? DEFAULT_BASE_URL
                : configured.trim();
        return StringUtils.removeEnd(baseUrl, "/");
    }
}
