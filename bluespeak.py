#!/usr/bin/python
# coding: utf-8

import dbus
import dbus.service
import dbus.mainloop.glib
import time
import gobject
import logging

class Agent(dbus.service.Object):
    exit_on_release = True

    def set_exit_on_release(self, exit_on_release):
        self.exit_on_release = exit_on_release

    @dbus.service.method("org.bluez.Agent",
                    in_signature="", out_signature="")
    def Release(self):
        print "Release"
        if self.exit_on_release:
            mainloop.quit()

    @dbus.service.method("org.bluez.Agent",
                    in_signature="os", out_signature="")
    def Authorize(self, device, uuid):
        print "Authorize (%s, %s)" % (device, uuid)
        authorize = raw_input("Authorize connection (yes/no): ")
        if (authorize == "yes"):
            return
        raise Rejected("Connection rejected by user")

    @dbus.service.method("org.bluez.Agent",
                    in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print "RequestPinCode (%s)" % (device)
        return raw_input("Enter PIN Code: ")

    @dbus.service.method("org.bluez.Agent",
                    in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        print "RequestPasskey (%s)" % (device)
        passkey = raw_input("Enter passkey: ")
        return dbus.UInt32(passkey)

    @dbus.service.method("org.bluez.Agent",
                    in_signature="ou", out_signature="")
    def DisplayPasskey(self, device, passkey):
        print "DisplayPasskey (%s, %06d)" % (device, passkey)

    @dbus.service.method("org.bluez.Agent",
                    in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        print "RequestConfirmation (%s, %06d)" % (device, passkey)
        confirm = raw_input("Confirm passkey (yes/no): ")
        if (confirm == "yes"):
            return
        raise Rejected("Passkey doesn't match")

    @dbus.service.method("org.bluez.Agent",
                    in_signature="s", out_signature="")
    def ConfirmModeChange(self, mode):
        print "ConfirmModeChange (%s)" % (mode)
        authorize = raw_input("Authorize mode change (yes/no): ")
        if (authorize == "yes"):
            return
        raise Rejected("Mode change by user")

    @dbus.service.method("org.bluez.Agent",
                    in_signature="", out_signature="")
    def Cancel(self):
        print "Cancel"

class Device:
    """Bluetooth device"""
    def __init__(self, address, properties):
        self.address = address
        self.init_properties(properties)

    def init_properties(self, properties):
        """Read properties and setup attributes"""
        self.name = properties['Name']
        self.paired = properties['Paired']
        self.classes = properties['Class']
        self.trusted = properties['Trusted']

    def _get_bluez_device(self, adapter):
        """Get from adapter Bluez device object"""
        if not self.paired:
            self.pair(adapter)

        try:
            return adapter.FindDevice(self.address)
        except dbus.exceptions.DBusException as e:
            if "org.bluez.Error.DoesNotExist" in str(e):
                logging.error('Device does not exist')
                return None

    def pair(self, bus, adapter):
        """Pair adapter with this device"""
        if self.paired == True:
            logging.info('Device %s already paired')
            return

        def create_device_reply(device):
            self.paired = True
            logging.info("New device (%s)" % (device))
            mainloop.quit()
        def create_device_error(error):
            logging.info("Creating device failed: %s" % (error))
            mainloop.quit()

        path = '/test/agent'
        capability = "DisplayYesNo"
        agent = Agent(bus, path)
        agent.set_exit_on_release(False)

        adapter.CreatePairedDevice(self.address, path, capability,
                    reply_handler=create_device_reply,
                    error_handler=create_device_error)

        mainloop = gobject.MainLoop()
        mainloop.run()

    def unpair(self, adapter):
        """Unpair adapter with this device"""
        device = self._get_bluez_device(adapter)
        adapter.RemoveDevice(device)
        self.paired = False


def get_adapter(bus, device_id=None):
    """From device id or default"""
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.bluez.Manager")

    try:
        if device_id is not None:
            adapter_path = manager.FindAdapter(device_id)
        else:
            adapter_path = manager.DefaultAdapter()
    except dbus.exceptions.DBusException as e:
        if "org.bluez.Error.NoSuchAdapter" in str(e):
            logging.error('No adapter available')
            return None

    return dbus.Interface(bus.get_object("org.bluez", adapter_path), "org.bluez.Adapter")

def discover(bus, adapter):
    """Add signals DeviceFound
       and PropertyChanged"""
    devices = []

    def device_found(address, properties):
        """Callback called each time
           a new device is detected"""
        for device in devices:
            if address == device.address:
                break
        else:
            devices.append(Device(address, properties))

    bus.add_signal_receiver(device_found,
                            dbus_interface="org.bluez.Adapter",
                            signal_name="DeviceFound")

    def property_changed(name, value):
        if name == "Discovering" and not value:
            mainloop.quit()

    bus.add_signal_receiver(property_changed,
                            dbus_interface="org.bluez.Adapter",
                            signal_name="PropertyChanged")

    adapter.StartDiscovery()
    mainloop = gobject.MainLoop()
    mainloop.run()

    return devices

def list_devices(bus, adapter):
    """List current devices"""
    devices = []

    for path in adapter.ListDevices():
        new_device = dbus.Interface(bus.get_object("org.bluez", path), "org.bluez.Device")
        properties = new_device.GetProperties()
        address = properties["Address"]

        for device in devices:
            if address == device.address:
                break
        else:
            devices.append(Device(address, properties))

    return devices

if __name__ == '__main__':
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = get_adapter(bus)
    if adapter is None:
        raise Exception('No adapter found')

    print 'List current devices'
    devices = list_devices(bus, adapter)
    for device in devices:
        print "Device %s" % device.address
        print "\tPaired: %s" %   device.paired
        if not device.paired:
            device.pair(bus, adapter)

    print 'Discover new devices'
    devices = discover(bus, adapter)
    for device in devices:
        print "Device %s" % device.address
        print "\tPaired: %s" %   device.paired
        if not device.paired:
            device.pair(bus, adapter)