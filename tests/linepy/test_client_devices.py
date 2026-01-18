"""Tests for linepy/client/devices.py."""

from src.linepy.client.devices import (
    DEVICE_TYPES,
    DEVICES,
    V3_SUPPORT_DEVICES,
    DeviceDetails,
    get_device_details,
    is_v3_support,
)


class TestDeviceDetails:
    """Tests for DeviceDetails dataclass."""

    def test_init(self):
        device = DeviceDetails(
            app_version="1.0.0",
            system_name="TestOS",
            system_version="10.0",
            app_type="TEST",
        )
        assert device.app_version == "1.0.0"
        assert device.system_name == "TestOS"
        assert device.system_version == "10.0"
        assert device.app_type == "TEST"

    def test_version_property(self):
        device = DeviceDetails(
            app_version="9.2.0.3403",
            system_name="WINDOWS",
            system_version="10.0.0-NT-x64",
            app_type="DESKTOPWIN",
        )
        assert device.version == "9.2.0.3403"

    def test_system_type_property(self):
        device = DeviceDetails(
            app_version="9.2.0.3403",
            system_name="WINDOWS",
            system_version="10.0.0-NT-x64",
            app_type="DESKTOPWIN",
        )
        expected = "DESKTOPWIN\t9.2.0.3403\tWINDOWS\t10.0.0-NT-x64"
        assert device.system_type == expected

    def test_default_app_type(self):
        device = DeviceDetails(
            app_version="1.0.0",
            system_name="Test",
            system_version="1.0",
        )
        assert device.app_type == ""


class TestDeviceTypes:
    """Tests for DEVICE_TYPES dictionary."""

    def test_desktopwin_exists(self):
        assert "DESKTOPWIN" in DEVICE_TYPES
        device = DEVICE_TYPES["DESKTOPWIN"]
        assert device.system_name == "WINDOWS"

    def test_desktopmac_exists(self):
        assert "DESKTOPMAC" in DEVICE_TYPES
        device = DEVICE_TYPES["DESKTOPMAC"]
        assert device.system_name == "MAC"

    def test_ios_exists(self):
        assert "IOS" in DEVICE_TYPES
        device = DEVICE_TYPES["IOS"]
        assert device.system_name == "iOS"

    def test_iosipad_exists(self):
        assert "IOSIPAD" in DEVICE_TYPES
        device = DEVICE_TYPES["IOSIPAD"]
        assert device.system_name == "iOS"

    def test_android_exists(self):
        assert "ANDROID" in DEVICE_TYPES
        device = DEVICE_TYPES["ANDROID"]
        assert device.system_name == "Android OS"

    def test_androidsecondary_exists(self):
        assert "ANDROIDSECONDARY" in DEVICE_TYPES
        device = DEVICE_TYPES["ANDROIDSECONDARY"]
        assert device.system_name == "Android OS"

    def test_watchos_exists(self):
        assert "WATCHOS" in DEVICE_TYPES
        device = DEVICE_TYPES["WATCHOS"]
        assert device.system_name == "watchOS"

    def test_wearos_exists(self):
        assert "WEAROS" in DEVICE_TYPES
        device = DEVICE_TYPES["WEAROS"]
        assert device.system_name == "Wear OS"

    def test_all_devices_have_app_type(self):
        for name, device in DEVICE_TYPES.items():
            assert device.app_type == name


class TestDevices:
    """Tests for DEVICES backward compatibility dictionary."""

    def test_contains_all_device_types(self):
        for device_name in DEVICE_TYPES:
            assert device_name in DEVICES

    def test_device_structure(self):
        for name, device in DEVICES.items():
            assert "version" in device
            assert "app_type" in device
            assert device["app_type"] == name


class TestV3SupportDevices:
    """Tests for V3_SUPPORT_DEVICES set."""

    def test_desktopwin_supports_v3(self):
        assert "DESKTOPWIN" in V3_SUPPORT_DEVICES

    def test_desktopmac_supports_v3(self):
        assert "DESKTOPMAC" in V3_SUPPORT_DEVICES

    def test_ios_supports_v3(self):
        assert "IOS" in V3_SUPPORT_DEVICES

    def test_android_supports_v3(self):
        assert "ANDROID" in V3_SUPPORT_DEVICES

    def test_androidsecondary_supports_v3(self):
        assert "ANDROIDSECONDARY" in V3_SUPPORT_DEVICES

    def test_iosipad_not_in_v3(self):
        assert "IOSIPAD" not in V3_SUPPORT_DEVICES

    def test_watchos_not_in_v3(self):
        assert "WATCHOS" not in V3_SUPPORT_DEVICES

    def test_wearos_not_in_v3(self):
        assert "WEAROS" not in V3_SUPPORT_DEVICES


class TestGetDeviceDetails:
    """Tests for get_device_details function."""

    def test_get_existing_device(self):
        device = get_device_details("DESKTOPWIN")
        assert device is not None
        assert device.app_type == "DESKTOPWIN"

    def test_case_insensitive(self):
        device = get_device_details("desktopwin")
        assert device is not None
        assert device.app_type == "DESKTOPWIN"

    def test_mixed_case(self):
        device = get_device_details("DesktopWin")
        assert device is not None
        assert device.app_type == "DESKTOPWIN"

    def test_nonexistent_device_returns_none(self):
        device = get_device_details("UNKNOWN_DEVICE")
        assert device is None

    def test_custom_version(self):
        device = get_device_details("DESKTOPWIN", version="1.2.3.4")
        assert device is not None
        assert device.app_version == "1.2.3.4"
        assert device.system_name == "WINDOWS"
        assert device.app_type == "DESKTOPWIN"

    def test_custom_version_preserves_other_fields(self):
        original = DEVICE_TYPES["IOS"]
        device = get_device_details("IOS", version="99.0.0")
        assert device.app_version == "99.0.0"
        assert device.system_name == original.system_name
        assert device.system_version == original.system_version

    def test_nonexistent_device_with_version_returns_none(self):
        device = get_device_details("UNKNOWN", version="1.0.0")
        assert device is None


class TestIsV3Support:
    """Tests for is_v3_support function."""

    def test_supported_devices(self):
        assert is_v3_support("DESKTOPWIN") is True
        assert is_v3_support("DESKTOPMAC") is True
        assert is_v3_support("IOS") is True
        assert is_v3_support("ANDROID") is True
        assert is_v3_support("ANDROIDSECONDARY") is True

    def test_unsupported_devices(self):
        assert is_v3_support("IOSIPAD") is False
        assert is_v3_support("WATCHOS") is False
        assert is_v3_support("WEAROS") is False

    def test_unknown_device(self):
        assert is_v3_support("UNKNOWN") is False

    def test_case_sensitive(self):
        # Function is case sensitive
        assert is_v3_support("desktopwin") is False
