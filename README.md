
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_gallery?name=astrbot_plugin_gallery&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_gallery

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 图库管理器 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 🤝 介绍

【本地图库管理器】-帮助用户组建、管理、调用本地图库，可用于表情包收集管理、图床管理、为其他插件提供动态图库等等

## 📦 安装

直接在astrbot的插件市场搜索astrbot_plugin_gallery，点击安装，等待完成即可

- 或者可以直接克隆源码到插件文件夹：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/Zhalslar/astrbot_plugin_gallery
# 控制台重启AstrBot
```

## ⌨️ 使用说明

`/图库帮助` - 查看以下的帮助菜单

| 命令 | 描述 | 示例用法 |
|------|------|----------|
| `/精准匹配词` | 查看精准匹配词 | `/精准匹配词` |
| `/模糊匹配词` | 查看模糊匹配词 | `/模糊匹配词` |
| `/模糊匹配 <图库名s>` | 将指定图库切换到模糊匹配模式 | `/模糊匹配 图库A 图库B` |
| `/精准匹配 <图库名s>` | 将指定图库切换到精准匹配模式 | `/精准匹配 图库A 图库B` |
| `/添加匹配词 <图库名> <匹配词s>` | 为指定图库添加匹配词 | `/添加匹配词 图库A 关键词1 关键词2` |
| `/删除匹配词 <图库名> <匹配词s>` | 为指定图库删除匹配词 | `/删除匹配词 图库A 关键词1 关键词2` |
| `/设置容量 <图库名> <容量>` | 设置指定图库的容量上限 | `/设置容量 图库A 100` |
| `/开启压缩 <图库名s>` | 打开指定图库的压缩开关 | `/开启压缩 图库A 图库B` |
| `/关闭压缩 <图库名s>` | 关闭指定图库的压缩开关 | `/关闭压缩 图库A 图库B` |
| `/开启去重 <图库名s>` | 打开指定图库的去重开关 | `/开启去重 图库A 图库B` |
| `/关闭去重 <图库名s>` | 关闭指定图库的去重开关 | `/关闭去重 图库A 图库B` |
| `/存图 <图库名> <序号>` | 存图到指定图库，序号指定时会替换掉原图，图库名不填则默认自己昵称，也可 @他人作为图库名 | `/存图 图库A 1` 或 `/存图 @昵称 1` |
| `/删图 <图库名> <序号s>` | 删除指定图库中的图片，序号不指定表示删除整个图库 | `/删图 图库A 1 2` 或 `/删图 图库A` |
| `/查看 <序号s/图库名>` | 查看指定图库中的图片或图库详情，序号指定时查看单张图片 | `/查看 图库A` 或 `/查看 1` |
| `/图库列表` | 查看所有图库 | `/图库列表` |
| `/图库详情 <图库名>` | 查看指定图库的详细信息 | `/图库详情 图库A` |
| `/(引用图片)/路径 <图库名>` | 查看指定图片的路径，需指定在哪个图库查找 | `/(引用图片)/路径 图库A` |
| `/(引用图片)/解析` | 解析图片的信息 | `/(引用图片)/解析` |

## ⌨️ 配置

请前往插件配置面板进行配置

## 🤝 TODO

- [x] 支持保存、删除、查看图片/图库
- [x] 支持批量保存、批量删除图片
- [x] 支持精准/模糊匹配模糊匹配关键词发图，并提供开关
- [x] 支持在图库里搜索图片
- [x] 支持解析图片信息
- [x] 支持设置图库容量
- [x] 自动压缩图片，并提供压缩开关
- [x] 自动去重，并提供去重开关
- [x] 权限控制
- [x] 支持热重载（存图、删图实时生效）
- [x] 支持将批量图片拖入文件夹进行加载
- [x] LLM调用图片
- [ ] 自动收集图片

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 由于要实现的功能繁多，目前仅确保图库的各种基本功能，后续会完善到完整体
- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）
