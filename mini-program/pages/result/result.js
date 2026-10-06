const results = [
  { title: '材料收纳王', tagline: '东西都能装进清单，但别忘了装水。', risk: '材料准备得很齐，却可能把最重要的那张通知压在最下面。', mission: '先看报到材料和流程，把“必须带”和“现场办”分开。', guide: '报到流程', target: 'page4', sprite: 0, tags: ['清单控', '稳稳入园'] },
  { title: '报到路线探险家', tagline: '地图是建议，走错才是剧情。', risk: '很有可能提前半小时出门，然后在校园里解锁隐藏路线。', mission: '先收藏交通路线和校区地图，再放心探索。', guide: '报到路线', target: 'page4', sprite: 1, tags: ['探索派', '地图依赖'] },
  { title: '流程速通特工', tagline: '不绕路、不排错队，开学第一关直接通关。', risk: '过于相信自己的效率，容易漏看一个小小的附件要求。', mission: '先用报到清单核对一次，再开启速通模式。', guide: '报到流程', target: 'page4', sprite: 2, tags: ['效率派', '流程玩家'] },
  { title: '新生情报联络员', tagline: '消息不是等来的，是问出来的。', risk: '群消息看了很多，但可能还没把真正有用的那条收藏。', mission: '把新手村和厦园小助手当成你的第一座情报站。', guide: '全局目录', target: 'page-overview', sprite: 3, tags: ['社交派', '情报雷达'] },
  { title: '选课研究员', tagline: '先研究规则，再抢心仪课程。', risk: '研究到最后一秒，页面可能已经开始排队。', mission: '先看选课系统和培养方案，再做你的课程计划。', guide: '选课系统', target: 'page6', sprite: 4, tags: ['学业派', '规则研究'] },
  { title: '课程副本探险家', tagline: '每门课都像一张等待解锁的新地图。', risk: '看到新课程就想试，最后发现时间表有自己的想法。', mission: '先了解选课和体育课规则，再安排你的课程副本。', guide: '体育选课', target: 'page5', sprite: 5, tags: ['探索派', '课程收藏'] },
  { title: 'GPA算分小树鸮', tagline: '先把每一分的去向算清楚。', risk: '别人还在问“这是什么”，你已经开始做公式表了。', mission: '先看学分、GPA 和培养方案，别让每一分变成谜语。', guide: '学分绩点综测', target: 'page11', sprite: 6, tags: ['算分派', '学业雷达'] },
  { title: '学习搭子组织者', tagline: '一个人纠结，不如一起研究。', risk: '很容易把一个简单问题开成一场小型圆桌会议。', mission: '和同学一起看选课、GPA 和培养方案，效率会更高。', guide: '培养方案档案', target: 'page8', sprite: 7, tags: ['社交派', '学习搭子'] },
  { title: '综测预警雷达', tagline: '别等评奖时，才想起综合测评。', risk: '看到“综测”两个字就想打开所有相关通知。', mission: '先区分评奖评优综测和推免综测，再收藏对应办法。', guide: '学分绩点综测', target: 'page11', sprite: 8, tags: ['规划派', '信息敏感'] },
  { title: '竞赛副本探险家', tagline: '看到赛道就想试试。', risk: '报名很积极，赛程和截止日期需要有人提醒。', mission: '先用专业竞赛匹配库找到适合自己的赛道。', guide: '专业竞赛', target: 'page10', sprite: 9, tags: ['成长派', '副本玩家'] },
  { title: '奖学金机会猎人', tagline: '通知更新速度比闹钟还重要。', risk: '收藏了很多办法，偶尔忘了回头看附件。', mission: '先看奖助学金和学院评奖办法，把时间节点单独记下来。', guide: '奖助学金', target: 'page9', sprite: 10, tags: ['机会派', '通知雷达'] },
  { title: '资源情报局长', tagline: '你知道的，最好大家都知道。', risk: '容易成为群里被@最多的人。', mission: '先把常用网站、资料区和官方入口整理成自己的工具箱。', guide: '常用网站', target: 'page7', sprite: 11, tags: ['社交派', '资源整合'] },
  { title: '宿舍生活管家', tagline: '先把自己的生活半径安排明白。', risk: '还没报到，已经开始研究宿舍附近吃什么。', mission: '先看公共设施、快递点和校园生活入口。', guide: '公共设施', target: 'page13', sprite: 12, tags: ['生活派', '提前安顿'] },
  { title: '迷路探险家', tagline: '到处走走，迟早走成学长。', risk: '可能在去食堂的路上，顺便参观了三个校区。', mission: '先收藏地图和报到路线，迷路也要迷得有准备。', guide: '报到流程', target: 'page4', sprite: 13, tags: ['探索派', '路线随机'] },
  { title: '校园效率特工', tagline: '能三分钟解决，绝不浪费三十分钟。', risk: '对网页入口、办事路径和排队时间有异常敏感。', mission: '从全局目录开始，把常用入口一次性收进工具箱。', guide: '全局目录', target: 'page-overview', sprite: 14, tags: ['效率派', '工具控'] },
  { title: '食堂外交官', tagline: '先交朋友，再研究哪家最好吃。', risk: '第一周的社交半径可能从宿舍扩展到整个食堂。', mission: '先熟悉公共设施、校园生活，再慢慢解锁你的社团和食堂地图。', guide: '公共设施', target: 'page13', sprite: 15, tags: ['社交派', '生活玩家'] }
];

Page({
  data: {
    result: results[0],
    typeIndex: 0,
    spriteStyle: 'background-position: 0 0;'
  },

  onLoad(options) {
    let typeIndex = Number(options.type);
    if (!Number.isInteger(typeIndex) || typeIndex < 0 || typeIndex >= results.length) typeIndex = 0;
    const result = results[typeIndex];
    const col = result.sprite % 4;
    const row = Math.floor(result.sprite / 4);
    this.setData({ result, typeIndex, spriteStyle: `background-position: ${col * 33.333333}% ${row * 33.333333}%;` });
  },

  openVillage() {
    wx.navigateTo({ url: `/pages/village/village?target=${this.data.result.target}` });
  },

  restart() {
    wx.reLaunch({ url: '/pages/index/index' });
  },

  copyShare() {
    const text = `我测出来是“${this.data.result.title}”，你是哪种厦大新生？`;
    wx.setClipboardData({ data: text, success: () => wx.showToast({ title: '分享文案已复制', icon: 'none' }) });
  },

  onShareAppMessage() {
    const result = this.data.result;
    return {
      title: `我测出来是“${result.title}”，你是哪种厦大新生？`,
      path: `/pages/result/result?type=${this.data.typeIndex}`,
      imageUrl: '/assets/xiayuan-share-cover.png'
    };
  },

  onShareTimeline() {
    return {
      title: `新生入园生存图鉴｜我是${this.data.result.title}`,
      query: `type=${this.data.typeIndex}`
    };
  }
});
