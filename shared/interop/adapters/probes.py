from shared.interop.contracts import AdapterCapability, AdapterStatus

def probe_eeglab() -> AdapterCapability:
    return AdapterCapability(
        adapter_name="eeglab",
        supported_formats=[".set", ".fdt"],
        dependency="eeglabio",
        availability=False,
        streaming_support=False,
        montage_support=False,
        write_support=False,
        status=AdapterStatus.UNAVAILABLE,
    )

def probe_fieldtrip() -> AdapterCapability:
    return AdapterCapability(
        adapter_name="fieldtrip",
        supported_formats=[".mat"],
        dependency="scipy",
        availability=False,
        streaming_support=False,
        montage_support=False,
        write_support=False,
        status=AdapterStatus.UNAVAILABLE,
    )

def probe_nwb() -> AdapterCapability:
    try:
        import pynwb
        return AdapterCapability(
            adapter_name="nwb",
            supported_formats=[".nwb"],
            dependency="pynwb",
            availability=True,
            streaming_support=True,
            montage_support=True,
            write_support=True,
            status=AdapterStatus.INTEGRATED,
        )
    except ImportError:
        return AdapterCapability(
            adapter_name="nwb",
            supported_formats=[".nwb"],
            dependency="pynwb",
            availability=False,
            streaming_support=False,
            montage_support=False,
            write_support=False,
            status=AdapterStatus.UNAVAILABLE,
        )

def probe_brainflow() -> AdapterCapability:
    try:
        import brainflow
        return AdapterCapability(
            adapter_name="brainflow",
            supported_formats=[],
            dependency="brainflow",
            availability=True,
            streaming_support=True,
            montage_support=False,
            write_support=False,
            status=AdapterStatus.INTEGRATED,
        )
    except ImportError:
        return AdapterCapability(
            adapter_name="brainflow",
            supported_formats=[],
            dependency="brainflow",
            availability=False,
            streaming_support=False,
            montage_support=False,
            write_support=False,
            status=AdapterStatus.UNAVAILABLE,
        )

def probe_lsl() -> AdapterCapability:
    try:
        import pylsl
        return AdapterCapability(
            adapter_name="lsl",
            supported_formats=[],
            dependency="pylsl",
            availability=True,
            streaming_support=True,
            montage_support=False,
            write_support=False,
            network_requirement="local",
            status=AdapterStatus.INTEGRATED,
        )
    except ImportError:
        return AdapterCapability(
            adapter_name="lsl",
            supported_formats=[],
            dependency="pylsl",
            availability=False,
            streaming_support=False,
            montage_support=False,
            write_support=False,
            network_requirement="local",
            status=AdapterStatus.UNAVAILABLE,
        )
