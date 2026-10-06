const { VILLAGE_URL } = require('../../utils/config');

Page({
  data: {
    ready: false,
    url: '',
    target: ''
  },

  onLoad(options) {
    const target = options.target || '';
    if (VILLAGE_URL && /^https:\/\//.test(VILLAGE_URL)) {
      this.setData({ ready: true, url: VILLAGE_URL, target });
      return;
    }
    this.setData({ ready: false, target });
  },

  showConfigHint() {
    wx.showModal({
      title: '还差一步配置',
      content: '请在 utils/config.js 填入线上 HTTPS 网站地址，并在微信公众平台配置业务域名。个人主体小程序可能无法使用 web-view。',
      showCancel: false
    });
  }
});
