# Cache Meter

[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md)

**缓存什么都记得——直到你切换模型。**

Cache Meter 把本地 Codex 会话日志变成一份 Codex 忘了放在同一个地方的报告：缓存命中与未命中、切换模型或 reasoning effort 造成的损失、恢复时间、按 API 标价折算的成本、自然重置时间，以及可选的 Tibo 全局重置“水晶球”。

一次切换让缓存骤冷时，Cache Meter 会估算有多少 cached tokens 蒸发了，以及同样的流量按公开 API 价目表要花多少钱。如果金额看起来像一小笔基础设施预算，先别慌：这只是按 API 标价折算的金额，不是你的 Codex 账单。一条命令、本地 JSONL、不用在 dashboard 里探险、不调用账户 API、不安装任何 Python 依赖。

```text
| Scope           | Input | Cache hit | Cache miss | Hit rate | Output | API equivalent |
|-----------------|-------|-----------|------------|----------|--------|----------------|
| Latest request  | 33.2K | 32.5K     | 662        | 98.0%    | 1.2K   | $0.04          |
| Current task    | 98.8K | 81.2K     | 17.6K      | 82.1%    | 4.8K   | $0.20          |

| Period          | Switches | Drops ≥20 pp | Est. lost cache | API equivalent |
|-----------------|----------|--------------|-----------------|----------------|
| Today           | 2        | 2            | 139.2K          | $0.50          |
| Rolling 30 days | 12       | 11           | 1.37M           | $4.20          |
```

## 显示内容

- 最近一次请求、当前任务、今天和滚动 30 天的缓存指标。
- 模型与 reasoning effort 的切换次数、显著的缓存命中率下降、预计损失的 cached tokens，以及恢复所需的调用次数。
- 每个范围的完整 API 折算成本，包括 cached input、cache miss、已报告的 cache write、output，以及超过 272K 的请求按每次调用所用模型公开价格计算的 long-context 倍率。
- 对已识别的 GPT-5.6 模型，仅使用 uncached input 与 cached input 的价格差计算缓存损失的 API 折算成本。
- Codex 提供数据时，显示 5 小时窗口和每周窗口的自然重置时间。
- 在 Codex App 中逐条显示每个可用的 banked reset 及其到期时间。
- 来自 `codex-resets.com` 的可选第三方 Tibo 重置预测。

美元金额按公开 API 价目表折算，不是 Codex 订阅的实际扣费。未知模型不计入金额估算；部分或推断出的估算会加上 `~`。价格以 [OpenAI 官方模型比较](https://developers.openai.com/api/docs/models/compare)为准。

## 安装

```sh
codex plugin marketplace add ivkiwi/codex-cache-meter
codex plugin add cache-meter@cache-meter
```

然后运行：

```text
/cache-meter
```

跳过公开预测请求：

```text
/cache-meter --no-tibo
```

## 隐私

Cache Meter 的 Python 部分读取 `$CODEX_HOME/sessions`（或 `~/.codex/sessions`）下的本地 JSONL 会话文件，不访问 Codex 凭据或账户 API。在 Codex App 中，技能通过内置的只读用量限制工具获取 banked-reset 状态，并省略账户和 credit ID。

除非使用 `--no-tibo`，否则它会向 `https://codex-resets.com/api/v1/status` 发出一次无需认证的只读 GET 请求。该预测来自第三方，并非 OpenAI 的承诺。

## 要求

- 带有本地会话日志的 Codex App 或 CLI。
- Python 3.10 或更高版本。
- 无 Python 依赖。

## 测试

```sh
python3 -m unittest discover -s tests
```

## 许可证

[MIT](LICENSE) · 由 Ivan 与 Ada 打造。
