# EPOS4HQ PbPb / OO correlation workflow

中文运行说明。仓库整理自 2026-11-20 核对的服务器代码，提供模拟配置、精简 HTCondor 提交层、独立 MB 中心度和核心 Δφ 计算。**不会自动提交、释放、取消或覆盖已有任务。**

## 先看这三点

1. **本版本是 r4 兼容性重构，不是新的物理结果。** 同源、切选、中心度、误差传播及 ROOT 对象定义保持原样。
2. **OS−SS 仍是服务器 r4 已实现的“原始事件差汇总，最后面积归一化”。** 用户后来要求的“每个正净面积事件先归一化、零/负面积单列”是不同观测量；本次没有悄悄替换，也不声称 r4 已实现它。详见 [方法定义](docs/METHODS.zh.md)。
3. `configs/historical` 是复现历史样本的配置，**不是推荐的修正生产配置**：PbPb 仍为 A=207、两系统衰变列表仍有差异。修正这些属于物理变更，需要新样本和独立版本，见 [已知问题](docs/KNOWN_ISSUES.zh.md)。

## 目录

```text
configs/historical/    原样 PbPb、OO、hq.i 参数
simulation/           共用的 PbPb/OO 原生生成器入口和 ROOT 验证器
workflow/core.py      来源证据、唯一粲载体联接、运动学、电荷及多重数
workflow/centrality.py 独立 MB 百分位、并列哈希拆分、标定验证
workflow/observables.py 同源跨阶段队列、OS/SS/OS−SS、迁移与记忆统计
workflow/bootstrap.py 一次生成并联合复用事件/MB bootstrap 抽样
workflow/root_output.py TH1D/TH2D、误差及协方差输出
workflow/campaign.py  冻结输入、解析/复用、MB、DAG 和验收编排
scripts/             创建独立计算目录、生成模拟批次、校验参考来源
tests/               新旧回归、完整 ROOT 比较、精简提交层检查
reference/           下载的旧版科学代码与模拟参考，仅作回归基线
docs/                方法、运行步骤、已知问题、验收范围
```

`reference/` 的旧脚本包含原服务器路径；**不要直接提交其中的历史 `.sub` 文件**。新提交文件由 `scripts/prepare_simulation.py` 或 `workflow/campaign.py` 生成，不添加 CPU/内存/磁盘请求、节点名单、Requirements、Rank、传输模式或并发限制。站点默认规则仍然适用。

## 本地验证

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
make test
```

仓库仅使用合成样本做可公开复现的测试。额外的真实 PbPb/OO 小样本回归已经本地执行；数据不上传。可用 `EPOS_REAL_FIXTURES=/private/sample/directory make test` 重做该检查。

## 服务器使用

分析依赖已有、通过来源审计的 lineage v5 生成器及其兼容 v4 缓存。**官网原版 EPOS4HQ 没有这些标签，不能直接冒充严格同源数据。** 不含生成器二进制、第三方安装库、模拟结果和整批输入清单。

```bash
git clone https://github.com/FDUEnrich/epos4hq-correlation-workflow.git
cd epos4hq-correlation-workflow
```

- [模拟配置与提交](docs/SIMULATION.zh.md)
- [独立 MB、解析复用及分析运行](docs/RUNNING.zh.md)
- [核心观测量定义](docs/METHODS.zh.md)
- [新旧一致性测试范围](docs/VALIDATION.zh.md)

## 官方资源与来源

- [EPOS4HQ 官方项目](https://klaus.pages.in2p3.fr/epos4/highlights/epos4hq.html)
- [官方安装页](https://klaus.pages.in2p3.fr/epos4/code/install.HQ.0.3.html)
- [HQ 参数手册](https://klaus.pages.in2p3.fr/epos4/pdf/hqManual.pdf)
- [ROOT 输出字段手册](https://klaus.pages.in2p3.fr/epos4/pdf/outputRoot.pdf)

原始参考文件校验值见 `reference/SOURCE_MANIFEST.json`。EPOS 派生文件及数据表遵循其原始许可；本仓库不对用户自有代码擅自声明统一开源许可，保持私有，参见 `NOTICE.md`。
