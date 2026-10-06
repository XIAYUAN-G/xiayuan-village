/* 厦园新手村 · 栏目单一数据源（4.1 起）
   侧边栏、总览分区卡片、内容页 iframe、通行码白名单、全局搜索元信息
   全部由这份清单生成；新增或调整栏目只需要改这里。
   字段说明：
   id          面板/按钮锚点，同时用于 hash 路由（#/page6?anchor=xxx）
   label/desc  侧边栏木牌文案
   short/shortDesc  总览分区卡片文案
   icon        小怪头像加载前的 emoji 兜底
   monster     侧边栏小怪立绘 [文件名, 无障碍描述]
   src         内容页 iframe 地址，更新页面后请顺带更新 ?v= 版本号
   public      false = 需要通行码解锁（进阶内容）
*/
window.XMU_NAV = {
  version: '20260929-plan-latest-sync-v4',
  overviewId: 'page-overview',
  /* 侧边栏当前保留课表 / 校园资料；美食资讯暂时隐藏，页面文件保留。
     具体攻略栏目不再出现在侧栏，统一从「校园资料」（原全局栏目总览）进入。 */
  sidebar: [
    { id: 'page-timetable', icon: '🗓️', monster: ['xmu-monster-calendar-v1.webp', '课表小帮手'], label: '课表', desc: '整周课表 · 导入管理', public: true },
    { id: 'page-overview', icon: '🗂️', monster: ['xmu-monster-01.webp', '校园资料入口'], label: '校园资料', desc: '全部攻略 · 按分区浏览', public: true },
    { id: 'page-piao', icon: '🚄', monster: ['xmu-monster-08.webp', '拼票小站长'], label: '拼票', desc: '曲线回家 · 省钱还能沿途玩', public: true }
  ],
  groups: [
    {
      key: 'newcomer',
      title: '新生入园',
      overviewKicker: '入园第一步',
      overviewSub: '先把开学安排准备好',
      items: [
        { id: 'page-overview', icon: '🗂️', monster: ['xmu-monster-01.webp', '校园资料入口'], label: '校园资料', desc: '全部攻略 · 按分区浏览', short: '校园资料', shortDesc: '一页查看全部入口', public: true, src: '' },
        { id: 'page16', icon: '📅', monster: ['xmu-monster-calendar-v1.webp', '校历小鼹鼠'], label: '校历', desc: '时间地图 · 学期、假期与重要日期', short: '校历', shortDesc: '开学、放假与重要日期', public: true, src: 'pages/厦门大学2026-2027学年校历.html?v=20260930-calendar-icon-toggle-v2' },
        { id: 'page4', icon: '🧭', monster: ['xmu-monster-01.webp', '报到流程小狐狸'], label: '报到流程', desc: '主线任务 · 入村第一关', short: '报到流程', shortDesc: '材料、迎新点与入校交通', public: true, src: 'pages/厦大新生报到流程及交通指南.html?v=20260812-mobile-layout-v3' },
        { id: 'page18', icon: '🪖', monster: ['xmu-monster-military-v1.webp', '军训小怪'], label: '军训指南', desc: '全副武装 · 训练、免减训与物资', short: '军训指南', shortDesc: '训练、免减训与物资准备', public: true, src: 'pages/厦大军训指南.html?v=20260817-military-training-v8' },
        { id: 'page1', icon: '📝', monster: ['xmu-monster-02.webp', '开学考试小猫头鹰'], label: '开学考试', desc: '入村情报 · 先摸清规则', short: '开学考试', shortDesc: '考试入口、时间与准备说明', public: true, src: 'pages/厦大新生入学考试查询.html?v=20260827-source-v4' }
      ],
      overviewIds: ['page16', 'page4', 'page18', 'page1']
    },
    {
      key: 'life',
      title: '校园生活',
      overviewKicker: '校园日常',
      overviewSub: '办事、生活和校园服务',
      items: [
        { id: 'page7', icon: '💻', monster: ['xmu-monster-03.webp', '常用工具小蘑菇'], label: '常用工具', desc: '工具箱 · 网站、电话与校园办事服务', short: '常用工具', shortDesc: '网站、电话与办事入口', public: true, src: 'pages/厦大新手必备网站.html?v=20260928-tools-search-guanwang-v18' },
        { id: 'page13', icon: '🏛️', monster: ['xmu-monster-facilities-v2.webp', '公共设施小浣熊'], label: '公共设施', desc: '校园工具 · 自习、体育、医疗与服务', short: '公共设施', shortDesc: '自习、体育、医疗与服务', public: true, src: 'pages/厦大公共设施指南.html?v=20260817-mobile-layout-v5' },
        { id: 'page17', icon: '🎪', monster: ['xmu-monster-04.webp', '学生社团小松鼠'], label: '学生社团', desc: '学生组织 · 学生会、团总支与社团', short: '学生社团', shortDesc: '学生会、团总支与社团', public: true, src: 'pages/厦大学生会社团指南.html?v=20260817-student-orgs-v8' },
        { id: 'page3', icon: '📦', monster: ['xmu-monster-05.webp', '快递点小浣熊'], label: '快递点地图', desc: '补给路线 · 包裹不迷路', short: '快递点地图', shortDesc: '各校区快递点与地址写法', public: true, src: 'pages/厦大快递点地图.html?v=20260812-mobile-layout-v4' },
        { id: 'page6', icon: '📚', monster: ['xmu-monster-06.webp', '本科选课小刺猬'], label: '本科选课系统指南', desc: '新手教程 · 按图完成选课', short: '本科选课', shortDesc: '选课入口与系统操作', public: true, src: 'pages/本科学生选课系统操作指南.html?v=20260814-course-selection-v1' }
      ],
      overviewIds: ['page7', 'page13', 'page3', 'page17']
    },
    {
      key: 'academic',
      title: '学业基础',
      overviewKicker: '课程与成绩',
      overviewSub: '选课、培养方案和绩点',
      items: [
        { id: 'page5', icon: '🏃', monster: ['xmu-monster-08.webp', '体育选课小青蛙'], label: '体育选课', desc: '体力挑战 · 抢到心仪项目', short: '体育选课', shortDesc: '项目、顺序与考核说明', public: true, src: 'pages/厦大体育选课指南.html?v=20260827-source-v4' },
        { id: 'page8', icon: '🗂️', monster: ['xmu-monster-10.webp', '培养方案小绵羊'], label: '培养方案档案', desc: '学业地图 · 查课程与专业必修', short: '培养方案档案', shortDesc: '课程结构与毕业学分', public: true, src: 'pages/厦大本科培养方案档案.html?v=20260929-plan-latest-sync-v4' },
        { id: 'page9', icon: '🏆', monster: ['xmu-monster-12.webp', '绩点综测小树鸮'], label: '绩点综测奖学金', desc: '成长补给 · 学业表现、综测与资助', short: '绩点综测奖学金', shortDesc: 'GPA、综测与奖助学金', public: true, src: 'pages/厦大奖助学金与学分绩点综测指南.html?v=20260830-study-support-gpa-v13' }
      ],
      overviewIds: ['page6', 'page5', 'page8', 'page9']
    },
    {
      key: 'growth',
      title: '发展方向',
      overviewKicker: '选择下一条路线',
      overviewSub: '转专业、竞赛与升学规划',
      items: [
        { id: 'page0', icon: '🔄', monster: ['xmu-monster-07.webp', '转专业小乌龟'], label: '往届转专业政策参考', desc: '支线任务 · 探索新方向', short: '转专业政策', shortDesc: '可转入口与政策参考', public: false, src: 'pages/厦大转专业政策查询.html?v=20260814-transfer-reference-v1' },
        { id: 'page2', icon: '🎓', monster: ['xmu-monster-09.webp', '双学位小变色龙'], label: '双学位政策查询', desc: '进阶副本 · 解锁第二技能', short: '双学位政策', shortDesc: '项目、辅修与申请规则', public: false, src: 'pages/厦大双学位政策.html?v=20260814-dual-degree-v1' },
        { id: 'page10', icon: '🏅', monster: ['xmu-monster-11.webp', '竞赛小水獭'], label: '专业竞赛', desc: '成长副本 · 找到适合你的赛道', short: '专业竞赛', shortDesc: '竞赛方向与官方入口', public: false, src: 'pages/厦大专业竞赛智能匹配库.html?v=20261001-dl-btn-fix-v3' },
        { id: 'page12', icon: '🦌', monster: ['xmu-monster-13.webp', '保研小鹿'], label: '关于保研', desc: '升学路线 · 从资格到确认', short: '保研导航', shortDesc: '资格、流程与系统确认', public: false, src: 'pages/保研导航.html?v=20261001-dl-btn-fix-v3' }
      ],
      overviewIds: ['page0', 'page2', 'page10', 'page12']
    },
    {
      key: 'materials',
      title: '学术资料',
      overviewKicker: '查资料和方法',
      overviewSub: '论文、资料与共享档案',
      overviewWide: true,
      items: [
        { id: 'page14', icon: '📜', monster: ['xmu-monster-paper-squirrel.webp', '论文小松鼠'], label: '论文期刊科普', desc: '学术支线 · 选刊、分类与学院核对', short: '论文期刊科普', shortDesc: '选刊、分类与学院核对', public: false, src: 'pages/论文发表科普指南.html?v=20260824-paper-system-v3' },
        { id: 'page15', icon: '📚', monster: ['xmu-monster-materials-v2.webp', '资料小熊'], label: '资料存放区', desc: '共享档案 · 搜索与下载资料', short: '资料存放区', shortDesc: '搜索与下载共享资料', public: false, src: 'pages/资料存放区.html?v=20260817-materials-v6' }
      ],
      overviewIds: ['page14', 'page15']
    }
  ]
};

/* 按 id 查找栏目条目（含侧栏四板块与全部分组栏目） */
window.XMU_NAV_ITEM = function (id) {
  for (const group of window.XMU_NAV.groups) {
    const found = group.items.find(item => item.id === id);
    if (found) return found;
  }
  return (window.XMU_NAV.sidebar || []).find(item => item.id === id) || null;
};
