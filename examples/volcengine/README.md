# 火山引擎端到端对话

这是本仓库的一个功能：对着麦克风说话，程序把声音发给火山引擎端到端对话，再把回复从扬声器播出来。仓库整体说明见 [README.md](../../README.md)。

有两个脚本，都在仓库根目录运行：

- `examples/volcengine/mic_chat.py`：普通聊天。模型根据自身知识回答。
- `examples/volcengine/mic_chat_rag.py`：带本地知识库。问到知识库里的内容时，程序先查出原文，再交给火山引擎端到端对话说出来。

下面按第一次使用的顺序写。每一步做完再做下一步。

## 1. 先准备这些东西

火山引擎端到端对话的 API Key。登录火山引擎控制台，在语音技术的 API Key 管理里创建。Key 只放在仓库根目录你自己的 `.env` 里。

## 2. 安装依赖

在仓库根目录打开终端，执行：

```bash
pip install -e ".[rag]"
```

`rag` 是本地检索。只跑普通对话时可以写成 `pip install -e .`。

## 3. 填写密钥

在仓库根目录复制一份配置文件：

```bash
cp .env.example .env
```

用文本编辑器打开 `.env`，把下面这一行填上你的 Key：

```bash
SEEDUPLEX_API_KEY=这里换成你的Key
```

可选的两行（不写就用代码里的默认值）：

```bash
SEEDUPLEX_MODEL=1.2.6.1
SEEDUPLEX_SPEAKER=zh_male_m191_uranus_bigtts
```

- `SEEDUPLEX_MODEL` 是模型版本。当前接口要求 `1.2.6.1`。
- `SEEDUPLEX_SPEAKER` 是说话的音色。默认是 `zh_male_m191_uranus_bigtts`。换成控制台音色列表里的其他音色 ID 即可。

程序启动时先读系统环境变量。环境变量里没有，再读仓库根目录的 `.env`。所以如果你在终端里已经 `export` 过同名变量，`.env` 里的值不会覆盖它。

## 4. 确认麦克风和扬声器

```bash
python examples/volcengine/mic_chat.py --list-devices
```

终端会列出声卡编号。记下有输入的设备编号，以及有输出的设备编号。

如果列表里有名字包含 `AIUI-USB-MC` 的麦克风，脚本会自动用它。PM01 上的这块麦固定是 8 声道，人声在第 2 到 5 路，脚本会把这几路合成一路再上传。第 6、7 路是扬声器回采，留给以后的回声消除，不会混进上传的语音。其他麦克风按单声道打开。

扬声器默认走系统默认输出。要指定设备时加上编号，例如输入是 0、输出是 3：

```bash
python examples/volcengine/mic_chat.py --input-device 0 --output-device 3
```

## 5. 开始普通对话

```bash
python examples/volcengine/mic_chat.py
```

看到「对着麦克风说话」后，直接说话。终端会打印识别出的文字和火山引擎端到端对话的回复，扬声器同时播放语音。结束时按 `Ctrl+C`。

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--list-devices` | 只列出声卡，然后退出 |
| `--input-device 编号` | 指定麦克风 |
| `--output-device 编号` | 指定扬声器 |
| `--greet` | 连上后先说一句「你好，我在。」 |
| `--duplex` | 播报时继续上传麦克风。只有麦克风自己能消除回声时才用 |

默认是半双工：对方说话时，程序暂停上传你的声音，改成上传同样长度的静音。这样喇叭里的声音不会被当成你的下一句话。静音仍然要继续发，否则服务端会因为收不到音频而超时，后面再说话也不会有回复。

## 6. 开始带知识库的对话

知识库正文是 `data/knowledge_text.txt`。换成你自己的资料时，用 UTF-8 编码保存成纯文本，再用 `--knowledge` 指向它。

```bash
python examples/volcengine/mic_chat_rag.py
python examples/volcengine/mic_chat_rag.py --knowledge data/knowledge_text.txt
```

启动时会先打印切成了多少段。你问到资料里的门店、公司或产品时，终端会出现 `[检索]` 和命中段数，然后火山引擎端到端对话根据查到的原文回答。资料里没有的内容，它应该说不知道。

这个脚本的麦克风参数和 `examples/volcengine/mic_chat.py` 相同，也可以加 `--greet`、`--duplex` 和设备编号。

检索方式是本地 BM25：把文本按大约 512 字切成段，用 jieba 分词后做关键词匹配，取得分最高的几段原文。`src/engineai_robotics_chat/knowledge/stopwords.txt` 里的词会在打分前去掉，避免「一个」「一些」这类常见词把不相关的段落排到前面。这里没有向量模型，也没有调用云端知识库。

## 7. 提示词和会话设置

连上服务后，程序做的第一件事是发送 `session.create`。这一条消息里，和「怎么听、怎么答」有关的设置如下。改完任何一项，都要重新运行脚本，已经连上的会话不会自己更新。

官方说明：系统提示词、服务端内置提示和对话上下文加在一起，上限大约 12K tokens。知识库全文不要贴进提示词，只放规则和主题范围。正文放在 `data/knowledge_text.txt`，需要时再检索。

### instructions：系统提示词

字段位置：`session.instructions`。

这是给模型的人设和回答规则。模型每次回答都会参考它。它不出现在扬声器里，用户听不到这段文字。

普通对话用 `src/engineai_robotics_chat/providers/volcengine/prompt.py` 里的 `CHAT_INSTRUCTIONS`。当前规则是：

1. 用用户的语言回答。用户说中文就用中文，说英文就用英文。
2. 口语化，通常一两句。用户明确要求详细说明时再展开。
3. 不输出舞台动作、括号说明和拟声词。
4. 听不清、噪声、无意义数字串时保持沉默，也不要说出「我保持沉默」。
5. 闲聊和一般问题用模型自己的知识回答。不确定就简短说明，不编造具体数字。
6. 不提及模型厂商、接口名称，也不说自己是云服务。

带知识库的对话不用上面这一份，而用 `examples/volcengine/mic_chat_rag.py` 里的 `RAG_INSTRUCTIONS`。它保留了语言、长度和口语的要求，并加上：

1. 知识库覆盖的主题要写在提示词里，让模型知道什么问题该查资料。当前写的是门店、公司和产品。
2. 问到这些事实时，必须调用一次 `retrieve`，`query` 填用户这句话。回答只能依据查回来的原文。
3. 没有查到就说不知道，不编造价格、参数或日期。
4. 打招呼和与资料无关的闲聊直接回答，不要调用 `retrieve`。
5. 口头不要出现接口名、BM25、检索或工具名。

要改口吻、身份或回答长短，就改对应的那一段字符串。普通聊天改 `CHAT_INSTRUCTIONS`，知识库聊天改 `RAG_INSTRUCTIONS`。两份互不影响。

### tools：函数说明

字段位置：`session.tools`。

普通聊天这里是空的，模型不会调用工具。

知识库聊天会放上一个名为 `retrieve` 的函数。函数的 `description` 和参数说明也是提示词，模型靠它们决定要不要查、以及 `query` 里该填什么。当前说明要求：问到知识库覆盖的主题时调用一次，并只根据返回的原文回答。

调用发生后，服务端发来 `response.function_call_arguments.done`。程序在本地检索，再用同一个 `call_id` 把原文交回去。交回去之前，模型不会继续说这一轮的答案。

### hotwords：识别热词

字段位置：`extension.asr.extra.context.hotwords`。

热词是说给语音识别的，不是说给回答模型的。专有名词容易听错时放在这里，例如产品型号。知识库脚本当前设置了「众擎」「PM01」「T800」。普通聊天默认是空的。

在 `examples/volcengine/mic_chat_rag.py` 里改 `cfg.hotwords = [...]` 即可。每个词是一个字符串。

### location：对话地点

字段位置：`extension.dialog.location`。

这是告诉模型「当前对话发生在哪里」，方便回答天气、附近一类和地点有关的问题。默认写在 `src/engineai_robotics_chat/providers/volcengine/config.py` 的 `DialogConfig.location`，包括经纬度、城市、省市区和地址。地点变了就改这一个字典。

### audit_response：审核兜底话术

字段位置：`extension.dialog.extra.audit_response`。

用户的问题命中服务端安全审核时，模型用这段固定英文回复，而不是继续回答原问题。当前文案在 `src/engineai_robotics_chat/providers/volcengine/client.py` 的 `build_session_config` 里。要改语气或改成中文，改这一个字符串。

### 其他会随会话一起发出的开关

这些在 `extension.dialog.extra` 里，默认值如下：

| 字段 | 当前值 | 含义 |
| --- | --- | --- |
| `enable_loudness_norm` | 开 | 把回复音量调得更均匀 |
| `enable_music` | 关 | 不开唱歌 |
| `enable_volc_websearch` | 关 | 不使用火山的公开网页搜索 |

`enable_volc_websearch` 打开后，模型可以搜索公开网页。那不是这里的本地知识库。本地资料只走 `examples/volcengine/mic_chat_rag.py` 的 `retrieve`。若以后要开联网，还要在同一处配置搜索类型和对应的搜索 Key。

### 音频格式

这些不是提示词，但必须和麦克风、扬声器一致，否则会听不清或播放变调。

| 方向 | 格式 |
| --- | --- |
| 上传 | 16 kHz、单声道、16 位小端 PCM。大约每 20 毫秒一包，一包 640 字节 |
| 播放 | 24 kHz、单声道、16 位小端 PCM |

## 8. 遇到问题时先看这里

- 提示缺少 API Key：`.env` 不在仓库根目录，或 `SEEDUPLEX_API_KEY` 等号右边是空的。
- 连上了但完全不回话：看启动日志里的输入设备。`AIUI-USB-MC` 必须使用第 2 到 5 路；如果 1 秒内峰值只有个位数，说明采到的是静音。
- 播报后下一句没有反应：上行音频中断了。保持脚本继续发送静音，不要在播报期间把发送停掉。
- 知识库问题答非所问：先看终端有没有 `[检索]`。没有，就是提示词没有让模型调用 `retrieve`，检查 `RAG_INSTRUCTIONS` 和工具说明是否还在。有检索但内容不对，检查 `data/knowledge_text.txt` 里是否真有这句话，以及问题里是否包含资料里的关键词。
