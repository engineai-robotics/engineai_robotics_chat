# 豆包麦克风对话

从 `engineai_deployment` 的 `agent_manager.duplex` 抽出的豆包端到端实时语音客户端。
这里只保留对话 API（建连、推麦克风 PCM、收回复文本和 TTS），不含导航和后台 Agent。

接口：`wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue`  
鉴权头：`X-Api-Key`  
上行音频：16 kHz / 单声道 / s16le PCM  
下行音频：24 kHz / 单声道 / s16le PCM

## 准备

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 SEEDUPLEX_API_KEY
```

密钥与机器人部署里的 Seeduplex Key 相同。

## 对话

```bash
python mic_chat.py --list-devices
python mic_chat.py
python mic_chat.py --input-device 0 --output-device 6
python mic_chat.py --greet
```

默认半双工：助手说话时暂停上传麦克风，避免喇叭回声触发下一轮。声卡自带回声消除时用 `--duplex`。

`AIUI-USB-MC` 是 8 声道麦，人声在第 2–5 路。脚本会打开全部声道，把这几路混成单声道再上传。扬声器走系统默认输出（本机经 PulseAudio 到 USB Audio Device）。

对着麦克风说话即可。终端会打印识别文本和助手回复，扬声器播放语音。`Ctrl+C` 结束。
