const { api, ensureBoot } = require('../../utils/api');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        materials: [],
        expanded: {},
    },

    onShow() {
        this.load(this.data.state !== 'ready');
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => api('structure'))
            .then((materials) => {
                const expanded = {};
                materials.forEach((m, i) => {
                    expanded[m.id] = i === 0;
                });
                this.setData({ state: 'ready', materials: materials, expanded: expanded });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load(true);
    },

    toggle(event) {
        const id = event.currentTarget.dataset.id;
        const expanded = Object.assign({}, this.data.expanded);
        expanded[id] = !expanded[id];
        this.setData({ expanded: expanded });
    },

    goPractice() {
        wx.navigateTo({ url: '/pages/practice/practice' });
    },

    goCards() {
        getApp().globalData.reviewMode = false;
        wx.switchTab({ url: '/pages/cards/cards' });
    },
});
