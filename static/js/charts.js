const Charts = {
  _instances: {},
  _colors: ['#4A9EFF', '#ffb869', '#4caf50', '#e91e63', '#9c27b0', '#00bcd4', '#ff9800', '#607d8b'],

  _getOrCreate(el) {
    const id = el.id || el.dataset.chartId || ('chart-' + Math.random().toString(36).slice(2, 8));
    if (!el.id) el.id = id;
    if (this._instances[id]) {
      this._instances[id].dispose();
    }
    const chart = echarts.init(el, Charts._currentTheme || 'intentDark');
    this._instances[id] = chart;
    return chart;
  },

  _handleResize() {
    Object.values(Charts._instances).forEach(c => {
      if (!c.isDisposed()) c.resize();
    });
  },

  intentDistribution(el, data) {
    const chart = this._getOrCreate(el);
    const items = data.slice().reverse();
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 10, right: 60, top: 10, bottom: 10, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#414752', type: 'dashed' } }, axisLabel: { color: '#8a919e' } },
      yAxis: {
        type: 'category',
        data: items.map(x => humanize(x.intent)),
        axisLabel: { color: '#c0c7d4', fontSize: 11, width: 160, overflow: 'truncate' },
        axisLine: { show: false }, axisTick: { show: false },
      },
      series: [{
        type: 'bar',
        data: items.map(x => x.count),
        barMaxWidth: 20,
        itemStyle: { color: '#4A9EFF', borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', formatter: '{c}', color: '#8a919e', fontSize: 11 },
      }],
    });
    return chart;
  },

  intentDonut(el, data) {
    const chart = this._getOrCreate(el);
    const total = data.reduce((a, b) => a + b.count, 0);
    chart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: p => `<b>${p.name}</b><br/>Count: ${p.value} (${p.percent}%)`,
      },
      legend: {
        orient: 'vertical', right: 10, top: 'center',
        textStyle: { color: '#c0c7d4', fontSize: 11, fontFamily: 'JetBrains Mono' },
        formatter: name => {
          const item = data.find(d => humanize(d.intent) === name);
          return item ? `${name}  ${item.percentage}%` : name;
        },
      },
      series: [{
        type: 'pie', radius: ['45%', '72%'], center: ['30%', '50%'],
        avoidLabelOverlap: false,
        label: {
          show: true, position: 'center', fontSize: 22, fontWeight: 'bold', color: '#e0e2eb',
          formatter: () => total.toString(),
        },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: 'bold', formatter: '{b}\n{c}' },
        },
        data: data.map((x, i) => ({
          value: x.count,
          name: humanize(x.intent),
          itemStyle: { color: this._colors[i % this._colors.length] },
        })),
      }],
    });
    return chart;
  },

  satisfactionHistogram(el, data) {
    const chart = this._getOrCreate(el);
    chart.setOption({
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: p => `Score: ${p[0].name}<br/>Count: ${p[0].value}`,
      },
      grid: { left: 40, right: 20, top: 10, bottom: 30 },
      xAxis: {
        type: 'category',
        data: data.map(h => h.range.split('-')[0]),
        axisLabel: { color: '#8a919e', fontSize: 10 },
        axisLine: { lineStyle: { color: '#414752' } },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: '#414752', type: 'dashed' } },
        axisLabel: { color: '#8a919e' },
      },
      series: [{
        type: 'bar',
        data: data.map((h, i) => ({
          value: h.count,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#ffb4ab' },
              { offset: 0.5, color: '#ffb869' },
              { offset: 1, color: '#4caf50' },
            ]),
          },
        })),
        barMaxWidth: 30,
        itemStyle: { borderRadius: [3, 3, 0, 0] },
      }],
    });
    return chart;
  },

  satisfactionByCategory(el, data, colorKey) {
    const chart = this._getOrCreate(el);
    const barColor = colorKey === 'tertiary' ? '#ffb869' : colorKey === 'green' ? '#4caf50' : '#4A9EFF';
    const items = data.slice().reverse();
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 10, right: 50, top: 5, bottom: 5, containLabel: true },
      xAxis: { type: 'value', max: 1, splitLine: { lineStyle: { color: '#414752', type: 'dashed' } }, axisLabel: { color: '#8a919e' } },
      yAxis: {
        type: 'category',
        data: items.map(x => humanize(x.intent || x.complexity || x.expertise || '')),
        axisLabel: { color: '#c0c7d4', fontSize: 11, width: 120, overflow: 'truncate' },
        axisLine: { show: false }, axisTick: { show: false },
      },
      series: [{
        type: 'bar',
        data: items.map(x => x.mean),
        barMaxWidth: 16,
        itemStyle: { color: barColor, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', formatter: p => p.value.toFixed(2), color: '#8a919e', fontSize: 11 },
      }],
    });
    return chart;
  },

  skillsQuadrant(el, data) {
    const chart = this._getOrCreate(el);
    const maxAct = Math.max(...data.map(q => q.activations), 1);
    const qColors = { CORE: '#4A9EFF', NOISY: '#ffb4ab', NICHE: '#ffb869', REMOVE: '#607d8b' };

    chart.setOption({
      tooltip: {
        trigger: 'item',
        formatter: p => {
          const d = p.data;
          return `<b>${humanize(d[3])}</b><br/>Activations: ${d[0]}<br/>Relevance: ${d[1]}%<br/>Quadrant: ${d[4]}`;
        },
      },
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
      xAxis: {
        name: 'Activation Frequency', nameLocation: 'center', nameGap: 30,
        nameTextStyle: { color: '#8a919e', fontSize: 11 },
        splitLine: { lineStyle: { color: '#414752', type: 'dashed' } },
        axisLine: { lineStyle: { color: '#414752' } },
        axisLabel: { color: '#8a919e' },
      },
      yAxis: {
        name: 'Relevance Rate (%)', nameLocation: 'center', nameGap: 40,
        nameTextStyle: { color: '#8a919e', fontSize: 11 },
        min: 0, max: 100,
        splitLine: { lineStyle: { color: '#414752', type: 'dashed' } },
        axisLine: { lineStyle: { color: '#414752' } },
        axisLabel: { color: '#8a919e' },
      },
      series: [{
        type: 'scatter',
        symbolSize: d => Math.max(12, Math.min(40, (d[0] / maxAct) * 40)),
        data: data.map(q => [q.activations, q.relevance_rate, q.activations, q.skill, q.quadrant]),
        itemStyle: {
          color: p => qColors[p.data[4]] || '#666',
          opacity: 0.8,
        },
        label: {
          show: true, position: 'top',
          formatter: p => humanize(p.data[3]),
          fontSize: 10, color: '#c0c7d4',
          overflow: 'truncate', width: 80,
        },
        emphasis: { itemStyle: { opacity: 1, shadowBlur: 10, shadowColor: 'rgba(74,158,255,0.4)' } },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: '#414752', type: 'dashed', width: 1 },
          data: [
            { yAxis: 50 },
            { xAxis: maxAct / 2 },
          ],
        },
        markArea: {
          silent: true,
          data: [
            [{ coord: [0, 50], itemStyle: { color: 'rgba(255,184,105,0.04)' } }, { coord: [maxAct / 2, 100] }],
            [{ coord: [maxAct / 2, 50], itemStyle: { color: 'rgba(74,158,255,0.04)' } }, { coord: [maxAct, 100] }],
            [{ coord: [0, 0], itemStyle: { color: 'rgba(96,125,139,0.04)' } }, { coord: [maxAct / 2, 50] }],
            [{ coord: [maxAct / 2, 0], itemStyle: { color: 'rgba(255,180,171,0.04)' } }, { coord: [maxAct, 50] }],
          ],
        },
      }],
      graphic: [
        { type: 'text', left: 65, top: 35, style: { text: 'NICHE', fill: '#ffb869', fontSize: 10, fontWeight: 'bold' } },
        { type: 'text', right: 35, top: 35, style: { text: 'CORE', fill: '#4A9EFF', fontSize: 10, fontWeight: 'bold' } },
        { type: 'text', left: 65, bottom: 55, style: { text: 'REMOVE', fill: '#607d8b', fontSize: 10, fontWeight: 'bold' } },
        { type: 'text', right: 35, bottom: 55, style: { text: 'NOISY', fill: '#ffb4ab', fontSize: 10, fontWeight: 'bold' } },
      ],
    });
    return chart;
  },
};

echarts.registerTheme('intentDark', {
  backgroundColor: 'transparent',
  textStyle: { color: '#c0c7d4', fontFamily: 'Inter' },
  title: { textStyle: { color: '#e0e2eb' } },
  legend: { textStyle: { color: '#c0c7d4' } },
  tooltip: {
    backgroundColor: '#272a30',
    borderColor: '#414752',
    textStyle: { color: '#e0e2eb', fontSize: 12 },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#414752' } },
    splitLine: { lineStyle: { color: '#414752', type: 'dashed' } },
    axisLabel: { color: '#8a919e' },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#414752' } },
    splitLine: { lineStyle: { color: '#414752', type: 'dashed' } },
    axisLabel: { color: '#8a919e' },
  },
  color: ['#4A9EFF', '#ffb869', '#4caf50', '#e91e63', '#9c27b0', '#00bcd4', '#ff9800', '#607d8b'],
});

echarts.registerTheme('intentLight', {
  backgroundColor: 'transparent',
  textStyle: { color: '#44474e', fontFamily: 'Inter' },
  title: { textStyle: { color: '#1a1c20' } },
  legend: { textStyle: { color: '#44474e' } },
  tooltip: {
    backgroundColor: '#ffffff',
    borderColor: '#c4c6d0',
    textStyle: { color: '#1a1c20', fontSize: 12 },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#c4c6d0' } },
    splitLine: { lineStyle: { color: '#dce0e6', type: 'dashed' } },
    axisLabel: { color: '#74777f' },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#c4c6d0' } },
    splitLine: { lineStyle: { color: '#dce0e6', type: 'dashed' } },
    axisLabel: { color: '#74777f' },
  },
  color: ['#2d7dd2', '#c87400', '#2e7d32', '#c62828', '#7b1fa2', '#00838f', '#e65100', '#455a64'],
});

Charts._currentTheme = 'intentDark';

Charts.updateTheme = function(themeName) {
  Charts._currentTheme = themeName;
  const ids = Object.keys(Charts._instances);
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const old = Charts._instances[id];
    const opt = old.getOption();
    old.dispose();
    const chart = echarts.init(el, themeName);
    chart.setOption(opt);
    Charts._instances[id] = chart;
  });
};

window.addEventListener('resize', Charts._handleResize);
