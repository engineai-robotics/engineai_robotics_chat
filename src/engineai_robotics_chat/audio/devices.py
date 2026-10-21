"""声卡枚举，以及 AIUI 麦克风阵列的声道布局。"""

from __future__ import annotations

import sounddevice as sd

# AIUI-USB-MC 硬件锁 8 声道 / 16 kHz。0、1 路几乎是静音，
# 2–5 是麦克风，6–7 是扬声器回采参考。
AIUI_MIC_CHANNELS = (2, 3, 4, 5)
AIUI_REF_CHANNELS = (6, 7)


def list_devices() -> None:
    print(sd.query_devices())
    default_in, default_out = sd.default.device
    print(f"默认输入={default_in}  默认输出={default_out}")


def pick_input_device(explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    for index, dev in enumerate(sd.query_devices()):
        name = str(dev["name"])
        if dev["max_input_channels"] > 0 and "AIUI" in name:
            return index
    return None


def capture_layout(device: int | None) -> tuple[int, list[int], list[int], str]:
    """返回 (打开声道数, 麦克风声道, 回采声道, 设备名)。"""

    info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
    name = str(info["name"])
    max_in = int(info["max_input_channels"])
    if "AIUI" in name and max_in >= 6:
        mic = [ch for ch in AIUI_MIC_CHANNELS if ch < max_in]
        ref = [ch for ch in AIUI_REF_CHANNELS if ch < max_in]
        return max_in, mic, ref, name
    return 1, [0], [], name


def output_device_name(device: int | None) -> str:
    if device is None:
        return "默认"
    return str(sd.query_devices(device)["name"])
