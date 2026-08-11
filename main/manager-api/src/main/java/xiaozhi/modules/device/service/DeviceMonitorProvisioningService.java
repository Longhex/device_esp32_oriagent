package xiaozhi.modules.device.service;

/**
 * Declares the device identity in device-monitor before MQTT-only OTA tries
 * to activate it. The operation is intentionally idempotent: repeating it
 * for an existing serial must not rotate MQTT credentials.
 */
public interface DeviceMonitorProvisioningService {

    void declareDevice(String serial, String batch);
}
