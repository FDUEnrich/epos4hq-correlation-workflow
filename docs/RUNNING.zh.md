# 独立分析运行与旧解析缓存复用

## 本地测试不是生产验收

`make test` 验证科学定义与原版一致，不能代替执行节点依赖测试或完整 MB 标定。服务器 Python 3.6 继续使用 `workflow/requirements-farm.txt` 的旧版冻结依赖；本地测试环境与之分开，不能混装进旧生产环境。

## 创建新目录

```bash
export EPOS_BASE=/storage/fdunphome/enrich/EPOS4HQ
export EPOS_REUSE_FROM="$EPOS_BASE/initial_source_memory_20261115_r3"
export EPOS_PYTHONHOME="$EPOS_BASE/ccbar_lineage_pilot_20260921/runtime_python36_20260928"
export EPOS_VENDOR_SOURCE="$EPOS_BASE/initial_source_memory_20261115/venv/lib/python3.6/site-packages"
python3 scripts/new_run.py "$EPOS_BASE/NEW_ANALYSIS_NAME"
cd "$EPOS_BASE/NEW_ANALYSIS_NAME"
```

可选 `EPOS_TAGGED_SOURCE`、`EPOS_OO_PRODUCTION` 覆盖读取的既有完成生产目录；`EPOS_PBPB_PRODUCTION` 可额外加入共用模拟入口生成的新 PbPb 完成批次。旧生产布局和新批次显式 source/install 路径均支持。默认输入顺序和选择不变，新增数据后不得冒用旧缓存完成标记。环境白名单写入新目录的 `site.env`，随计划封存，不依赖提交主机的登录环境。不要存放密码或令牌。

## 准备与检查顺序

```bash
./launch.sh prepare-runtime
./launch.sh prepare
./launch.sh prepare-reuse
condor_submit runtime_smoke.sub
```

执行节点 canary 成功且 `RUNTIME_SMOKE_PASS.json` 通过后：

```bash
./launch.sh seal
./launch.sh preflight
```

然后由操作者明确决定是否提交新的独立 DAG：

```bash
./launch.sh submit
```

**本次仅整理仓库，没有执行提交命令。** 不能直接编辑旧 r4 或 r3 的 PLAN、源码、完成标记，也不能覆盖原 ROOT。新目录必须使用新计划签名和自己的验收记录。

## 缓存复用的边界

默认读取旧 r3 完成缓存，核对其计划、源码、输入顺序、生成器电荷表、解析函数、每文件事件数及 gzip/checkpoint 校验值。

`workflow/core.py` 与 r4 原件保持逐字节一致；`output_events` 的 AST/函数正文不变。这避免仅因模块整理就绕开旧身份认证。复用的是已完成解析，不是伪造已完成中心度或误差结果。

去掉旧代码固定“必须刚好 1937 文件”的断言，改为要求缓存条目数严格等于本次冻结记录数；没有放宽逐文件来源和内容检查。

## DAG 的必要依赖

```text
PILOT -> CHECK -> MB -> CALIBRATION
SOURCES ------------------------> ANALYSIS
CALIBRATION --------------------> ANALYSIS
```

两个系统各 20,000 个完整 MB 事件，独立 pilot 先证明 iskip=0 生效。未经完整 MB 及独立验证集验收，中心度计算不会通过。失败不默认“忽略一个坏作业继续发布”。

新 DAG 文件不含人为 CPU/内存/磁盘请求、节点筛选、Rank 或并发限制。程序也不会释放、取消或修改其他任务。旧队列保持原样。

## 输出

成功时输出 `output/InitialCharmCorrelationEvolution.root`，保存传统 TH1D/TH2D、审计树、中心度标定与 provenance。既有目标文件存在时拒绝静默覆盖。具体路径和定义见 `METHODS.zh.md`。

当前默认科学定义是 r4 兼容模式。不要把输出解释成尚未实现的“正净面积事件逐事件归一化”版本。
