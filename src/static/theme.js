/* 地图主题：三页底图与道路配色的唯一来源。
   暗色给 bars（夜行地图），亮色给 bichi / michelin（日间美食地图）。
   attribution 逐字沿用各页原有文案，避免上游署名变化。 */
window.MAP_THEMES = {
    dark: {
        tile: {
            url: 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png?key=cb1_3h6n_1_0d49d482d013e94f5ae62bb2',
            options: {
                attribution: '&copy; OpenStreetMap contributors &copy; CARTO (dark)',
                subdomains: 'abcd',
                maxZoom: 20
            }
        },
        // 夜间底图上用低饱和冷灰，干道亮、支路暗
        road: {
            1: { color: '#8B84A8', weight: 3.2, opacity: 0.72 },  // 核心干道
            2: { color: '#6E6784', weight: 2.0, opacity: 0.52 },  // 主要干道
            3: { color: '#5A5470', weight: 1.2, opacity: 0.36 }   // 较长道路
        },
        btn: { on: '#241F30', off: '#171422', fg: '#EDE9F5' }
    },
    light: {
        tile: {
            url: 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png?key=cb1_3h6n_1_0d49d482d013e94f5ae62bb2',
            options: {
                attribution: '&copy; CartoDB No-Labels Map Projection',
                subdomains: 'abcd',
                maxZoom: 20
            }
        },
        // 浅色底图上用暖灰，越粗越深
        road: {
            1: { color: '#6E6558', weight: 3.4, opacity: 0.85 },  // 核心干道
            2: { color: '#8C8377', weight: 2.2, opacity: 0.62 },  // 主要干道
            3: { color: '#A79E92', weight: 1.3, opacity: 0.40 }   // 较长道路
        },
        btn: { on: '#FCF9F2', off: '#D9D2C6' }
    }
};
