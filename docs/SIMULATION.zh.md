# 模拟配置与精简提交

## 参数来源

`configs/historical/PbPb.optns` 对应已运行 lineage-v5 PbPb 分片的 4-event 模板；`OO.optns` 对应 output_1021 的 100-event 模板。能量均为 5020 GeV，流体、HQ 和强子级联开启。`hq.i` 原样保留，SHA256 为 `b11ff781a1187f864c772e43ae1ac0de26f2365b65fd2f7b0e96fa9267dcf6f4`。

PbPb 原始上层模板曾为 30 events、OO 为 80 events；实际批处理会覆盖 nfull。不能以原始模板事件数代替实际作业预算或保留事件数。

**PbPb A=207、两系统衰变列表差异和 iskip=1 被保留。** 修正后必须另建 profile、另标定，不允许向同一冻结批次混入不同物理配置。

## 复用已验证的生成器

当前服务器 v5 生成器 SHA256：

`e509ba6eae8ac43b3ac085ea4c52d6a98de2cd2867d13c5976eb3964bc1c2ac7`

PbPb 可用现有 `ccbar_lineage_pilot_20260921/large_v5repair_20261009_005500/{full_source,install}`；OO 可用 `OO/output_1021/_batch/runtime/{source,install}`。**本仓库不重新构建、替换或擅自修改这些生成器。** 普通官网版缺少 fdPair 等标签，不能通过这里的 v5 验证器。

## 生成一批新提交文件

以下仅生成文件，不提交作业。必须使用全新的输出目录，并自行确认新种子区间与全部历史批次不重叠。示例种子不构成全局未使用证明。

```bash
BASE=/storage/fdunphome/enrich/EPOS4HQ
python3 scripts/prepare_simulation.py \
  --system OO \
  --destination "$BASE/OO/NEW_BATCH_NAME" \
  --source "$BASE/OO/output_1021/_batch/runtime/source" \
  --install "$BASE/OO/output_1021/_batch/runtime/install" \
  --root "$BASE/root/root/bin/root" \
  --pythonhome "$BASE/ccbar_lineage_pilot_20260921/runtime_python36_20260928" \
  --hepmc-lib "$BASE/HepMC3/install/lib64" \
  --fastjet-lib "$BASE/fastjet/fastjet-install/lib" \
  --jobs 20000 --events 100 --seed-base 300000001
```

PbPb 使用 `--system PbPb`，换成对应的已验证 `full_source/install`，并明确给出每作业事件数及另一组未使用种子。所有输出、配置和源码检查通过后，操作者才可执行：

```bash
condor_submit "$BASE/OO/NEW_BATCH_NAME/_batch/simulation.sub"
```

**本次仓库整理没有执行这一步。**

## 保留的检查

- 每个作业独立目录，已存在的尝试拒绝覆盖，不自动重试。
- 每作业唯一 seedj，固定 seedi；检查种子范围，按事件预算只覆盖 nfull。
- 二进制和共享 hq.i 校验；原生 clinput 的表路径及固定 nodecay 初始化保持原生产逻辑。
- 正常结束、请求/跳过/保留事件闭合。
- FD_AUDIT/FD_SOURCE 记录完整性、来源证据、唯一初始/最终载体、ROOT 标签版本及分支长度。
- ROOT 验证器从原 ValidateOO 抽出共用入口，只改系统标签与函数名，逐行回归验证主体不变。
- 成功后保存校验清单与完成标记；失败保留全部尝试及日志。

原 OO 和新共用入口使用相同生成器二进制及同一物理选项时，结构与配对规则不变。本次只做渲染/回归/语法检查，**没有用新入口再生成完整物理样本**，不能把它说成新一轮全量已完成。

新 `.sub` 只保留入口、参数、目录、日志、失败保持及队列；不人为添加资源、节点或传输约束。`notification=Never` 禁止调度器邮件通知。管理员默认要求仍可能影响匹配。
