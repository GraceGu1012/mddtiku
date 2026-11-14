const { api, ensureBoot } = require('../../utils/api');
const common = require('../../utils/common');

const FILTERS = ['全部知识卡', '未学 / 未记住 / 有点模糊', '已记住（自评）'];

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        keyword: '',
        filterIndex: 0,
        filters: FILTERS,
        list: [],
        total: 0,
        rememberedCount: 0,
        reviewMode: false,
    },

    _cards: [],

    onLoad(options) {
        this.applyReviewMode(options);
    },

    onShow() {
        // 从首页「今日复习」入口进来时带全局标记
        const app = getApp();
        if (app.globalData && app.globalData.reviewMode) {
            app.globalData.reviewMode = false;
            this.applyReviewMode({ mode: 'review' });
        }
        this.load(this.data.state !== 'ready');
    },

    applyReviewMode(options) {
        if (options && options.mode === 'review') {
            if (!this.data.reviewMode) {
                this.setData({ reviewMode: true });
                wx.setNavigationBarTitle({ title: '今日复习' });
            }
        }
    },

    exitReview() {
        this.setData({ reviewMode: false });
        wx.setNavigationBarTitle({ title: '墨督督学习空间' });
        this.computeList();
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => api('catalog'))
            .then((catalog) => {
                this._cards = catalog.filter((q) => q.kind === 'card');
                this.setData({
                    state: 'ready',
                    total: this._cards.length,
                    rememberedCount: this._cards.filter((q) => q.rating === 'remembered').length,
                });
                this.computeList();
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    computeList() {
        const keyword = (this.data.keyword || '').trim().toLowerCase();
        const filterIndex = this.data.filterIndex;
        const reviewMode = this.data.reviewMode;
        const list = this._cards
            .filter((q) => {
                const haystack = (q.prompt + ' ' + (q.tags || []).join(' ')).toLowerCase();
                if (keyword && haystack.indexOf(keyword) < 0) {
                    return false;
                }
                if (reviewMode) {
                    // 复习模式：只看待巩固（未记住 / 有点模糊）的卡片
                    return q.rating === 'again' || q.rating === 'unsure';
                }
                if (filterIndex === 1) {
                    return q.rating !== 'remembered';
                }
                if (filterIndex === 2) {
                    return q.rating === 'remembered';
                }
                return true;
            })
            .map((q, i) => ({
                id: q.id,
                number: ('0' + (i + 1)).slice(-2),
                pills: common.pills(q),
                prompt: q.prompt,
                foot: q.material_name,
                ratingText: common.ratingName(q.rating),
            }));
        this.setData({ list: list });
    },

    handleRetry() {
        this.load(true);
    },

    onSearch(event) {
        this.setData({ keyword: event.detail.value });
        this.computeList();
    },

    onFilterChange(event) {
        this.setData({ filterIndex: Number(event.detail.value) });
        this.computeList();
    },

    goCard(event) {
        const id = event.currentTarget.dataset.id;
        wx.navigateTo({ url: '/pages/card-detail/card-detail?id=' + encodeURIComponent(id) });
    },
});
