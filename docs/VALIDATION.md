# Reproduce validation / 重现验证

Current preview results and their scope are in [0.8.0 verification](VALIDATION-0.8.0.md). The original private diagnostic logs are retained by the maintainer and are not required to use the Skill.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/*.test.cjs
python3 scripts/check_distribution.py
```

Browser regression checks opt in with REPRISE_BROWSER_TESTS=1 and require an available browser/runtime. Distribution checks use the documented offline Python build tools and retain their environments. See [release checks](RELEASE-CHECKLIST.md) and [graph contracts](GIT-GRAPH.md).

当前结果与边界见上方验证记录。每次运行单独报告环境、成功、失败和跳过项；不能把维护者运行、静态验包或历史截图当作外部用户成功。
