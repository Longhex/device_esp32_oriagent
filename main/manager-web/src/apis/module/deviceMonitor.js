import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

const BASE = () => `${getServiceUrl()}/agentDeviceMonitor`;

export default {
    // Danh sách thiết bị + trạng thái
    getDevices(callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/devices`)
            .method('GET')
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('getDevices failed:', err);
                RequestService.reAjaxFun(() => { this.getDevices(callback); });
            }).send();
    },
    // Chi tiết 1 thiết bị
    getDevice(serial, callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/devices/${serial}`)
            .method('GET')
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('getDevice failed:', err);
                RequestService.reAjaxFun(() => { this.getDevice(serial, callback); });
            }).send();
    },
    // Gửi lệnh điều khiển {action, params}
    sendCommand(serial, payload, callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/devices/${serial}/command`)
            .method('POST')
            .data(payload)
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('sendCommand failed:', err);
                RequestService.reAjaxFun(() => { this.sendCommand(serial, payload, callback); });
            }).send();
    },
    // Danh sách serial đã khai báo
    getSerials(callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/serials`)
            .method('GET')
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('getSerials failed:', err);
                RequestService.reAjaxFun(() => { this.getSerials(callback); });
            }).send();
    },
    // Khai báo serial {serial, batch}
    declareSerial(payload, callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/serials`)
            .method('POST')
            .data(payload)
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('declareSerial failed:', err);
                RequestService.reAjaxFun(() => { this.declareSerial(payload, callback); });
            }).send();
    },
    // Kích hoạt serial {serial, mac} -> trả MQTT credential
    activate(payload, callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/activate`)
            .method('POST')
            .data(payload)
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('activate failed:', err);
                RequestService.reAjaxFun(() => { this.activate(payload, callback); });
            }).send();
    },
    // Gỡ thiết bị (unbind)
    deleteSerial(serial, callback) {
        RequestService.sendRequest()
            .url(`${BASE()}/serials/${serial}`)
            .method('DELETE')
            .success((res) => { RequestService.clearRequestTime(); callback(res); })
            .networkFail((err) => {
                console.error('deleteSerial failed:', err);
                RequestService.reAjaxFun(() => { this.deleteSerial(serial, callback); });
            }).send();
    }
}
