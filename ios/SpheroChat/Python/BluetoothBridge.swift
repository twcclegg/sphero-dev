import CoreBluetooth
import Foundation

/// CoreBluetooth behind blocking calls, for the embedded Python's spherov2
/// (through `_sphero_ble` in PythonBridge.c and `sphero_dev.ios_adapter`).
///
/// Every call blocks its (Python) thread until done or timed out; CoreBluetooth
/// runs on `queue`. Notifications go to Python on a separate serial queue, so a
/// Python handler that writes back can't deadlock the Bluetooth queue.
final class BluetoothBridge: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate,
    @unchecked Sendable
{
    static let shared = BluetoothBridge()

    struct Failure: Error, CustomStringConvertible {
        let description: String
        init(_ d: String) { description = d }
    }

    private let queue = DispatchQueue(label: "sphero.bluetooth")
    private let notifyQueue = DispatchQueue(label: "sphero.bluetooth.notify")
    private let opLock = NSLock()  // one blocking operation at a time
    private var central: CBCentralManager!

    // Touched only on `queue`.
    private var found: [UUID: (name: String, peripheral: CBPeripheral)] = [:]
    private var connected: [UUID: CBPeripheral] = [:]
    private var characteristics: [UUID: [String: CBCharacteristic]] = [:]
    private var waiting: DispatchSemaphore?
    private var waitError: Error?
    private var servicesLeft = 0

    private let powered = DispatchSemaphore(value: 0)

    override private init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: queue)
    }

    // MARK: blocking operations

    func scan(timeout: Double) throws -> [[String: String]] {
        opLock.lock()
        defer { opLock.unlock() }
        try waitForPower()
        queue.sync {
            found = [:]
            central.scanForPeripherals(withServices: nil, options: nil)
        }
        Thread.sleep(forTimeInterval: max(0.5, timeout))
        return queue.sync {
            central.stopScan()
            return found.map { ["name": $0.value.name, "address": $0.key.uuidString] }
        }
    }

    func connect(_ address: String) throws {
        opLock.lock()
        defer { opLock.unlock() }
        try waitForPower()
        guard let id = UUID(uuidString: address) else { throw Failure("bad address \(address)") }
        let peripheral: CBPeripheral? = queue.sync {
            found[id]?.peripheral ?? central.retrievePeripherals(withIdentifiers: [id]).first
        }
        guard let peripheral else { throw Failure("The robot isn't in range any more.") }
        try wait(timeout: 10, what: "connecting") {
            peripheral.delegate = self
            self.central.connect(peripheral)
        }
        queue.sync {
            connected[id] = peripheral
            characteristics[id] = [:]
        }
        try wait(timeout: 10, what: "discovering the robot's services") {
            peripheral.discoverServices(nil)
        }
    }

    func disconnect(_ address: String) {
        opLock.lock()
        defer { opLock.unlock() }
        guard let id = UUID(uuidString: address) else { return }
        queue.sync {
            if let p = connected.removeValue(forKey: id) { central.cancelPeripheralConnection(p) }
            characteristics[id] = nil
        }
    }

    func subscribe(_ address: String, _ uuid: String) throws {
        opLock.lock()
        defer { opLock.unlock() }
        let (p, c) = try lookup(address, uuid)
        try wait(timeout: 5, what: "subscribing to \(uuid)") { p.setNotifyValue(true, for: c) }
    }

    func write(_ address: String, _ uuid: String, _ data: Data) throws {
        opLock.lock()
        defer { opLock.unlock() }
        let (p, c) = try lookup(address, uuid)
        try wait(timeout: 5, what: "writing to the robot") {
            p.writeValue(data, for: c, type: .withResponse)
        }
    }

    // MARK: helpers

    private func waitForPower() throws {
        if queue.sync(execute: { central.state == .poweredOn }) { return }
        if powered.wait(timeout: .now() + 5) == .timedOut {
            let state = queue.sync { central.state }
            switch state {
            case .unauthorized:
                throw Failure("Bluetooth permission is off for this app (Settings → Privacy).")
            case .poweredOff: throw Failure("Bluetooth is turned off.")
            default: throw Failure("Bluetooth isn't ready (state \(state.rawValue)).")
            }
        }
        powered.signal()  // leave it signalled for the next caller
    }

    private func lookup(_ address: String, _ uuid: String) throws -> (CBPeripheral, CBCharacteristic) {
        guard let id = UUID(uuidString: address) else { throw Failure("bad address \(address)") }
        return try queue.sync {
            guard let p = connected[id] else { throw Failure("Not connected to the robot.") }
            guard let c = characteristics[id]?[uuid.lowercased()] else {
                throw Failure("The robot has no characteristic \(uuid).")
            }
            return (p, c)
        }
    }

    /// Start an operation on `queue`, then block until a delegate callback calls `finish`.
    private func wait(timeout: Double, what: String, _ start: @escaping () -> Void) throws {
        let sem = DispatchSemaphore(value: 0)
        queue.sync {
            waiting = sem
            waitError = nil
            start()
        }
        if sem.wait(timeout: .now() + timeout) == .timedOut {
            queue.sync { waiting = nil }
            throw Failure("Timed out \(what).")
        }
        if let e = queue.sync(execute: { waitError }) { throw e }
    }

    private func finish(_ error: Error? = nil) {  // on `queue`
        waitError = error
        waiting?.signal()
        waiting = nil
    }

    // MARK: CBCentralManagerDelegate (on `queue`)

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn { powered.signal() }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let name = advertisementData[CBAdvertisementDataLocalNameKey] as? String ?? peripheral.name
        if let name { found[peripheral.identifier] = (name, peripheral) }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        finish()
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral,
                        error: Error?) {
        finish(error ?? Failure("Couldn't connect."))
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                        error: Error?) {
        connected[peripheral.identifier] = nil
        if waiting != nil { finish(error ?? Failure("The robot disconnected.")) }
    }

    // MARK: CBPeripheralDelegate (on `queue`)

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        let services = peripheral.services ?? []
        if let error { return finish(error) }
        servicesLeft = services.count
        if services.isEmpty { return finish(Failure("The robot has no services.")) }
        for s in services { peripheral.discoverCharacteristics(nil, for: s) }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                    error: Error?) {
        for c in service.characteristics ?? [] {
            characteristics[peripheral.identifier, default: [:]][c.uuid.uuidString.lowercased()] = c
        }
        servicesLeft -= 1
        if servicesLeft == 0 { finish() }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor c: CBCharacteristic,
                    error: Error?) {
        finish(error)
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor c: CBCharacteristic, error: Error?) {
        finish(error)
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error: Error?) {
        guard error == nil, let value = c.value else { return }
        let address = peripheral.identifier.uuidString
        let uuid = c.uuid.uuidString.lowercased()
        notifyQueue.async {
            value.withUnsafeBytes { buf in
                sd_python_notify(address, uuid, buf.bindMemory(to: UInt8.self).baseAddress,
                                 buf.count)
            }
        }
    }
}

// MARK: the C functions PythonBridge.c calls (declared in PythonBridge.h)

private func cString(_ s: String) -> UnsafeMutablePointer<CChar>? { strdup(s) }

private func errorString(_ body: () throws -> Void) -> UnsafeMutablePointer<CChar>? {
    do {
        try body()
        return nil
    } catch {
        return cString("\(error)")
    }
}

@_cdecl("sd_ble_scan")
func bleScan(_ timeout: Double) -> UnsafeMutablePointer<CChar>? {
    let list = (try? BluetoothBridge.shared.scan(timeout: timeout)) ?? []
    let data = (try? JSONSerialization.data(withJSONObject: list)) ?? Data("[]".utf8)
    return cString(String(decoding: data, as: UTF8.self))
}

@_cdecl("sd_ble_connect")
func bleConnect(_ address: UnsafePointer<CChar>) -> UnsafeMutablePointer<CChar>? {
    errorString { try BluetoothBridge.shared.connect(String(cString: address)) }
}

@_cdecl("sd_ble_disconnect")
func bleDisconnect(_ address: UnsafePointer<CChar>) {
    BluetoothBridge.shared.disconnect(String(cString: address))
}

@_cdecl("sd_ble_subscribe")
func bleSubscribe(_ address: UnsafePointer<CChar>, _ uuid: UnsafePointer<CChar>)
    -> UnsafeMutablePointer<CChar>?
{
    errorString { try BluetoothBridge.shared.subscribe(String(cString: address), String(cString: uuid)) }
}

@_cdecl("sd_ble_write")
func bleWrite(_ address: UnsafePointer<CChar>, _ uuid: UnsafePointer<CChar>,
              _ data: UnsafePointer<UInt8>, _ length: Int) -> UnsafeMutablePointer<CChar>?
{
    let bytes = Data(bytes: data, count: length)
    return errorString {
        try BluetoothBridge.shared.write(String(cString: address), String(cString: uuid), bytes)
    }
}
