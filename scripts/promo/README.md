# 15 秒探店地图宣传片

成片位于 `../../docs/media/shanghai-map-promo.mp4`，README 使用同名 GIF 直接展示全片。1920×1080、30 fps、15 秒、H.264 / AAC；GIF 为无声循环预览。

`editorial-plan.json` 记录分镜和时间点，`composition.html` 是按时间确定性渲染的动效源，`capture.cjs` 从真实 `dist/` 页面截图。影片中的相机移动属于剪辑效果；筛选和详情前后状态来自实际页面操作。所有数据与界面均未替换。

## 重现

依赖：Node.js + `playwright`，Chrome，Python 3 + `numpy`，FFmpeg / FFprobe。可用 `NODE_PATH` 指向已有包目录；`CHROME_PATH` 可覆盖 macOS Chrome 默认路径，`FFMPEG` 可覆盖编码器路径。

在仓库根目录执行：

```sh
# 可选：重新采集界面。另一个终端先运行 python3 -m http.server 8765。
node scripts/promo/capture.cjs http://127.0.0.1:8765/dist/

export PROMO_WORK=/tmp/shanghai-map-promo
mkdir -p "$PROMO_WORK"
python3 scripts/promo/make_audio.py "$PROMO_WORK/audio.wav"
node scripts/promo/render.cjs --stills  # 代表帧
node scripts/promo/render.cjs --draft   # 720p 预览
node scripts/promo/render.cjs           # 1080p 无声画面，450 帧

ffmpeg -y -i "$PROMO_WORK/picture.mp4" -i "$PROMO_WORK/audio.wav" \
  -map 0:v:0 -map 1:a:0 -c:v copy \
  -af 'loudnorm=I=-16:TP=-1.8:LRA=7,aresample=48000,atrim=0:15' \
  -c:a aac -b:a 192k -ar 48000 -t 15 -movflags +faststart \
  "$PROMO_WORK/final-candidate.mp4"

# 全量解码检查成功后再替换成片。
ffmpeg -v error -i "$PROMO_WORK/final-candidate.mp4" -f null -
cp "$PROMO_WORK/final-candidate.mp4" docs/media/shanghai-map-promo.mp4
ffmpeg -y -i docs/media/shanghai-map-promo.mp4 \
  -filter_complex '[0:v]fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3' \
  -loop 0 docs/media/shanghai-map-promo.gif
```

成片元数据、全量解码结果、响度与 SHA-256 在 `../../docs/media/promo-validation.json`；最终联系表和转场抽帧在 `../../docs/media/promo-contact.jpg`、`../../docs/media/promo-transitions.jpg`。更新成片后应重新生成这些验证资料。

## 来源与制作说明

- 页面：本仓库构建产物，采集证据与图片尺寸见 `sources/capture-report.json` 和 `sources/manifest.json`。
- 底图：OpenStreetMap contributors、CARTO。影片保留全程署名。数据源链接：<https://www.openstreetmap.org/copyright>、<https://carto.com/attributions>。
- 音乐：`make_audio.py` 原创合成，无外部采样、旁白或商业音乐。
- 字体：采集与渲染环境的 macOS 系统字体（苹方、宋体及系统无衬线）；不随仓库分发字体文件。其他系统可替换 CSS 字体栈。
- 数字：制作时上海餐饮合并去重 131 家、夜生活 37 处、首尔星级与必比登共 93 家。数据变化后可重新采集并更新影片。
