# Cache Meter

[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md)

**缓存什么都记得——直到你切换模型。**

Cache Meter 把本地 Codex 会话日志变成一份 Codex 忘了放在同一个地方的报告：缓存命中与未命中、切换模型或 reasoning effort 造成的损失、恢复时间、按 API 标价折算的成本、自然重置时间，以及可选的 Tibo 全局重置“水晶球”。

一次切换让缓存骤冷时，Cache Meter 会估算有多少 cached tokens 蒸发了，以及同样的流量按公开 API 价目表要花多少钱。如果金额看起来像一小笔基础设施预算，先别慌：这只是按 API 标价折算的金额，不是你的 Codex 账单。一条命令、本地 JSONL、不用在 dashboard 里探险、不调用账户 API、不安装任何 Python 依赖。

## 完整报告示例

2026 年 9 月 7 日的实际输出（Europe/Istanbul）。用量、价格、重置时间和预测均为当时的历史快照。

## Cache Meter

`gpt-6-astra` · `medium` · local JSONL

| Scope | Input | Cache hit | Cache miss | Hit rate | Output | API equivalent |
|---|---:|---:|---:|---:|---:|---:|
| Latest request | 34.9K | 20.5K | 14.4K | **58.6%** | 221 | **$0.18** |
| Current task | 34.9K | 20.5K | 14.4K | **58.6%** | 221 | **$0.18** |
| Today | 135.24M | 128.59M | 6.65M | **95.1%** | 529.6K | **~$136.69** |
| Rolling 30 days | 6.65B | 6.40B | 255.14M | **96.2%** | 22.84M | **~$3508.79** |

Current model base prices: input **$10.00/MTok** · cached **$1.00/MTok** · output **$50.00/MTok**.

### Cache continuity

| Period | Switches | Drops ≥20 pp | Est. lost cache | API equivalent |
|---|---:|---:|---:|---:|
| Today | 3 | 3 | 362.7K | **$2.75** |
| Rolling 30 days | 39 | 37 | 4.87M | **$17.63** |

30-day split: **8** model changes · **34** effort changes · **2.7** calls average recovery among recovered drops.

Latest material drop: `gpt-5.6-sol/max` → `gpt-5.6-sol/high` · **96.0%** → **0.0%** (−96.0 pp) · recovered in **7** calls · **95.5K** estimated cached tokens lost · **$0.34** API equivalent.

Current task: Model/effort steady at `gpt-6-astra/medium`.

Scope API equivalents include cached input, cache misses, reported cache writes, output, and >272K long-context multipliers at public per-call model prices. `~` marks partial or inferred pricing. The continuity equivalent is only the uncached-vs-cached price gap caused by estimated cache loss. Neither is billed Codex spend; unknown models are excluded. Continuity excludes auto-review and subagent traffic.

### Rate-limit runway

| Window | Used | Natural reset |
|---|---|---|
| 5 hours | — | Not exposed |
| Week | 10% [#-----------] | Mon 14 Sep, 09:46 |

### Tibo

**Next reset:** 45% · elevated · within 24h · until Mon 07 Sep, 23:09

> @Gelassoldat @rezoundous Who says it won't reset in a while 👀

Source: [@thsottiaux](https://x.com/thsottiaux/status/2096692394435752258)

**Banked reset announced:** Sat 05 Sep, 03:39 · [@thsottiaux](https://x.com/thsottiaux/status/2096035437299237298)

> Because we are beyond happy to have Astra rolled out today ahead of schedule and you have been super patient with us \(not really, but it’s ok\!\)… we will do the full banked reset today too for all Plus, Pro and Business users&#46; Lands end of day&#46; Happy Astra day and enjoy a phenomenal weekend&#46; PS&#58; If you create the account or upgrade before 8pm PT you will get it too&#46; Still time\!

### Banked resets

- **Full reset** — available · expires **Mon 21 Sep 2026, 03:00** (Europe/Istanbul)
- **Full reset** — available · expires **Sun 04 Oct 2026, 04:58** (Europe/Istanbul)
- **Full reset** — available · expires **Mon 05 Oct 2026, 07:18** (Europe/Istanbul)

---

## 显示内容

- 最近一次请求、当前任务、今天和滚动 30 天的缓存指标。
- 模型与 reasoning effort 的切换次数、显著的缓存命中率下降、预计损失的 cached tokens，以及恢复所需的调用次数。
- 每个范围的完整 API 折算成本，包括 cached input、cache miss、已报告的 cache write、output，以及超过 272K 的请求按每次调用所用模型公开价格计算的 long-context 倍率。
- 对已识别的模型（包括 GPT-6 Astra），仅使用 uncached input 与 cached input 的价格差计算缓存损失的 API 折算成本。
- Codex 提供数据时，显示 5 小时窗口和每周窗口的自然重置时间。
- 在 Codex App 中逐条显示每个可用的 banked reset 及其到期时间。
- 来自 `codex-resets.com` 的可选第三方 Tibo 重置预测。

美元金额按公开 API 价目表折算，不是 Codex 订阅的实际扣费。未知模型不计入金额估算；部分或推断出的估算会加上 `~`。若 CodexBar 可用，Cache Meter 会读取 TimeGate 同样使用的自动更新 `models.dev` 本地目录，因此新模型和价格变更无需发布新版插件即可生效。内置价格（包括 GPT-6 Astra）作为离线后备，并以 [OpenAI 官方模型比较](https://developers.openai.com/api/docs/models/compare)为准。

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

Cache Meter 的 Python 部分读取 `$CODEX_HOME/sessions`（或 `~/.codex/sessions`）下的本地 JSONL 会话文件，并在存在时读取 CodexBar 的本地模型价格缓存。它不会调用 CodexBar，也不访问 Codex 凭据或账户 API。在 Codex App 中，技能通过内置的只读用量限制工具获取 banked-reset 状态，并省略账户和 credit ID。

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
