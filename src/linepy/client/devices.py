"""Device type definitions and utilities."""

from dataclasses import dataclass


@dataclass
class DeviceDetails:
    """Device configuration details."""

    app_version: str
    system_name: str
    system_version: str
    app_type: str = ""

    @property
    def version(self) -> str:
        """Get the app version."""
        return self.app_version

    @property
    def system_type(self) -> str:
        """Get the system type header value."""
        return f"{self.app_type}\t{self.app_version}\t{self.system_name}\t{self.system_version}"


# Device types supported by LINE
DEVICE_TYPES = {
    "DESKTOPWIN": DeviceDetails(
        app_version="9.2.0.3403",
        system_name="WINDOWS",
        system_version="10.0.0-NT-x64",
        app_type="DESKTOPWIN",
    ),
    "DESKTOPMAC": DeviceDetails(
        app_version="9.2.0.3403",
        system_name="MAC",
        system_version="14.0.0-MacOSX-arm64",
        app_type="DESKTOPMAC",
    ),
    "IOS": DeviceDetails(
        app_version="15.19.0",
        system_name="iOS",
        system_version="18.0",
        app_type="IOS",
    ),
    "IOSIPAD": DeviceDetails(
        app_version="15.19.0",
        system_name="iOS",
        system_version="18.0",
        app_type="IOSIPAD",
    ),
    "ANDROID": DeviceDetails(
        app_version="14.21.0",
        system_name="Android OS",
        system_version="12",
        app_type="ANDROID",
    ),
    "ANDROIDSECONDARY": DeviceDetails(
        app_version="14.21.0",
        system_name="Android OS",
        system_version="12",
        app_type="ANDROIDSECONDARY",
    ),
    "WATCHOS": DeviceDetails(
        app_version="15.19.0",
        system_name="watchOS",
        system_version="11.0",
        app_type="WATCHOS",
    ),
    "WEAROS": DeviceDetails(
        app_version="3.3.0",
        system_name="Wear OS",
        system_version="4.0",
        app_type="WEAROS",
    ),
}

# Alias for backward compatibility
DEVICES = {k: {"version": v.app_version, "app_type": k} for k, v in DEVICE_TYPES.items()}

# Devices that support v3 login
V3_SUPPORT_DEVICES = {"DESKTOPWIN", "DESKTOPMAC", "IOS", "ANDROID", "ANDROIDSECONDARY"}


def get_device_details(device: str, version: str | None = None) -> DeviceDetails | None:
    """
    Get device details for a given device type.

    Args:
        device: The device type name (case insensitive)
        version: Optional custom version string

    Returns:
        DeviceDetails or None if device not supported
    """
    device_upper = device.upper()
    details = DEVICE_TYPES.get(device_upper)
    if details and version:
        return DeviceDetails(
            app_version=version,
            system_name=details.system_name,
            system_version=details.system_version,
            app_type=device_upper,
        )
    return details


def is_v3_support(device: str) -> bool:
    """
    Check if a device supports v3 login.

    Args:
        device: The device type name

    Returns:
        True if v3 login is supported
    """
    return device in V3_SUPPORT_DEVICES
