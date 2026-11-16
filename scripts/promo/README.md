# 24 秒七城探店地图宣传片

成片位于 `../../docs/media/shanghai-map-promo.mp4`。保留原路径以便旧下载链接继续获取新版；内容已经更新为七城十图。1920×1080、30fps、24秒（720帧）、H.264/AAC、48kHz立体声。README的GitHub附件播放器与仓库高清母版使用相同文件与SHA-256。

影片顺序：中国城市在前（上海、北京、苏州、南京、杭州、香港），韩国首尔在后。覆盖上海新版地图、四城名录、香港147条记录/146个点位，以及真实手机搜索与详情。杭州47条名录中46条已定位，影片不将全部名录数称为坐标点数。

## 编辑与来源

- `editorial-plan.json`：7段分镜、时长、镜头目的与验证要求。
- `composition.html`：与网站纸色/酒红风格一致的确定性动效源；所有时序由 `renderFrame(t)` 控制，无运行时随机或网络资源。
- `sources/capture-report.json`：真实页面、视口、裁切区域与操作证据。
- `sources/manifest.json`：构建HTML及每张截图的尺寸、文件大小和SHA-256。当前拍摄包含提交前工作区改动，不能仅用父提交SHA代替这些源哈希。
- `capture.cjs`：以实际页面控件复现采集。默认桌面1440×1240、移动430×960，支持 `--output`。此次交付源通过CUA捕获：桌面使用CDP截图避免表面重排，手机使用真实搜索、选店及滚动后的原生截图。图片内容未替换。
- `make_audio.py`：原创电钢琴、低音与轻鼓配乐，无外部采样。支持 `--duration`、`--plan`，默认24秒，末尾0.7秒淡出。
- `final-audio.ffgraph` / `render-plan.json`：合成与验证约定，目标响度−16 LUFS、真峰值不高于−1.5dBTP。

地图画面来自OpenStreetMap，影片全程保留署名。页面与剪辑使用系统字体，不在仓库中分发字体文件。没有把店铺说明改写成假界面，也没有用占位底图替换加载失败的瓦片。

## 重现

依赖：Node.js、Playwright、Chrome、Python3+NumPy、FFmpeg及FFprobe。`NODE_PATH`可指向已有包目录，`CHROME_PATH`指定Chrome，`FFMPEG`指定编码器。先在仓库根目录构建页面并运行本地HTTP服务：

```sh
python3 build.py
python3 -m http.server 8876 --bind 127.0.0.1
```

另一个终端：

```sh
node scripts/promo/capture.cjs http://127.0.0.1:8876/dist/ --output scripts/promo/sources
export PROMO_WORK=/tmp/city-atlas-promo
mkdir -p "$PROMO_WORK"
python3 scripts/promo/make_audio.py "$PROMO_WORK/audio.wav" --plan scripts/promo/editorial-plan.json
node scripts/promo/render.cjs --stills
node scripts/promo/render.cjs --draft
node scripts/promo/render.cjs
ffmpeg -y -i "$PROMO_WORK/picture.mp4" -i "$PROMO_WORK/audio.wav" \
  -filter_complex_script scripts/promo/final-audio.ffgraph \
  -map 0:v:0 -map '[aout]' -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart "$PROMO_WORK/final-candidate.mp4"
ffmpeg -v error -xerror -i "$PROMO_WORK/final-candidate.mp4" -f null -
```

完整验证和视觉检查成功后再替换成片。此项目也提供标准video-workbench格式的 `render-plan.json`，可进行验证通过后再自动提升候选文件的安全渲染。

动图生成：

```sh
ffmpeg -y -i docs/media/shanghai-map-promo.mp4 \
  -filter_complex '[0:v]fps=8,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3' \
  -loop 0 docs/media/shanghai-map-promo.gif
```

## 验证与发布

`../../docs/media/promo-validation.json`记录最终流信息、全解码、时长、帧率、响度和独立视觉QC。`promo-contact.jpg`、`promo-transitions.jpg`与`promo-poster.jpg`均来自最终母版；`SHA256SUMS`必须随MP4/GIF更新。

GitHub附件不是仓库文件的动态链接。更新视频后，要把新成片上传到Markdown编辑器附件区，将返回的新 `user-attachments` URL写入根README，并同步 `github-video.json`。不要复用旧视频UUID；无需为上传另外发布issue或评论。此次母版小于10MB，可直接用于原生播放器，无二次压缩。

旧版视频与截图在Git历史中可恢复，临时编码文件和复核帧不提交进仓库。
