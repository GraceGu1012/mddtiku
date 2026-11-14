const { api } = require('../../utils/api');
const common = require('../../utils/common');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        flipped: false,
        index: 0,
        total: 0,
        tagLine: '',
        prompt: '',
        answer: '',
        materialName: '',
        explanation: null,
        ratingList: [],
        rating: false,
    },

    _card: null,
    _cards: [],

    onLoad(options) {
        this.cardId = decodeURIComponent(options.id || '');
        this.load();
    },

    load() {
        this.setData({ state: 'loading', errorMsg: '' });
        Promise.all([api('cards/' + encodeURIComponent(this.cardId)), api('catalog')])
            .then((results) => {
                this._card = results[0];
                this._cards = results[1].filter((q) => q.kind === 'card');
                this.renderCard(false);
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load();
    },

    renderCard(flipped) {
        const q = this._card;
        const index = this._cards.findIndex((x) => x.id === q.id);
        this.setData({
            state: 'ready',
            flipped: flipped,
            index: index < 0 ? 0 : index,
            total: this._cards.length,
            tagLine: (q.tags || []).join(' · '),
            prompt: q.prompt,
            answer: q.answer || '',
            materialName: q.material_name || '',
            explanation: flipped ? common.buildExplanation(q) : null,
            ratingList: [
                { key: 'again', name: '未记住', primary: false },
                { key: 'unsure', name: '有点模糊', primary: false },
                { key: 'remembered', name: '已记住', primary: true },
            ],
            rating: false,
        });
    },

    onFlip() {
        this.renderCard(true);
    },

    onRate(event) {
        if (this.data.rating) {
            return;
        }
        const key = event.currentTarget.dataset.key;
        this.setData({ rating: true });
        api('cards/' + encodeURIComponent(this.cardId) + '/rating', {
            version: this._card.version,
            rating: key,
        })
            .then((result) => {
                const xp = result && result.xp ? result.xp : 0;
                wx.showToast({
                    title: '已保存：' + common.ratingName(key) + (xp > 0 ? ' · +' + xp + ' XP' : ''),
                    icon: 'none',
                });
                const next = this._cards[this.data.index + 1];
                if (next) {
                    wx.redirectTo({ url: '/pages/card-detail/card-detail?id=' + encodeURIComponent(next.id) });
                } else {
                    wx.switchTab({ url: '/pages/cards/cards' });
                }
            })
            .catch((err) => {
                wx.showToast({ title: err.message, icon: 'none' });
                this.setData({ rating: false });
            });
    },

    goCards() {
        wx.switchTab({ url: '/pages/cards/cards' });
    },

    goSource(event) {
        const sourceId = event.currentTarget.dataset.sourceId;
        wx.navigateTo({
            url:
                '/pages/source/source?itemId=' +
                encodeURIComponent(this.cardId) +
                '&sourceId=' +
                encodeURIComponent(sourceId),
        });
    },
});
