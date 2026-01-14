import { defineMermaidSetup } from '@slidev/types'

export default defineMermaidSetup(() => {
  return {
    theme: 'dark',
    themeVariables: {
      // 淡蓝色主题 (AWS Blue #00a1e0)
      primaryColor: 'rgba(0, 161, 224, 0.12)',
      primaryTextColor: '#ffffff',
      primaryBorderColor: '#00a1e0',
      lineColor: '#00a1e0',
      secondaryColor: 'rgba(0, 161, 224, 0.08)',
      tertiaryColor: 'rgba(77, 195, 240, 0.08)',
      background: '#0d1117',
      mainBkg: 'rgba(0, 161, 224, 0.12)',
      secondBkg: 'rgba(0, 161, 224, 0.08)',
      mainContrastColor: '#ffffff',
      darkMode: true,
      fontFamily: 'Amazon Ember, Helvetica Neue, Arial, sans-serif',
      fontSize: '16px',
      // 节点样式
      nodeBorder: '#00a1e0',
      nodeTextColor: '#ffffff',
      // 集群/分组样式
      clusterBorder: '#00a1e0',
      clusterBkg: 'rgba(0, 161, 224, 0.08)',
      // 边标签
      edgeLabelBackground: 'rgba(20, 30, 44, 0.9)',
      // 箭头
      arrowheadColor: '#00a1e0',
      // 流程图特定
      fillType0: 'rgba(0, 161, 224, 0.12)',
      fillType1: 'rgba(0, 161, 224, 0.08)',
      fillType2: 'rgba(77, 195, 240, 0.08)',
      // 线条粗细
      lineWidth: '2.5px',
      edgeWidth: '2.5px',
    },
    flowchart: {
      curve: 'basis',
      htmlLabels: true,
      useMaxWidth: true,
      nodeSpacing: 50,
      rankSpacing: 50,
    },
    sequence: {
      actorMargin: 50,
      boxMargin: 10,
      boxTextMargin: 5,
      noteMargin: 10,
      messageMargin: 35,
      mirrorActors: true,
      useMaxWidth: true,
      actorBkg: 'rgba(0, 161, 224, 0.12)',
      actorBorder: '#00a1e0',
      actorTextColor: '#ffffff',
      signalColor: '#00a1e0',
      signalTextColor: '#ffffff',
      noteBkgColor: 'rgba(0, 161, 224, 0.12)',
      noteBorderColor: '#4dc3f0',
      noteTextColor: '#ffffff',
    },
  }
})
