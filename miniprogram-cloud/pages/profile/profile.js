const { api, ensureBoot, getBoot } = require('../../utils/api');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        profileLabel: '学习档案',
        identityNote: '',
        attempts: 0,
        correctRate: '—',
        rememberedCount: 0,
        wrongCount: 0,
        cardCount: 0,
        menuItems: [],
    },

    onShow() {
        this.load(this.data.state !== 'ready');
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => Promise.all([api('catalog'), api('progress')]))
            .then((results) => {
                const catalog = results[0];
                const progress = results[1];
                const boot = getBoot() || {};
                const stats = progress.stats || { attempts: 0, correct: 0, today: 0 };
                const cards = catalog.filter((q) => q.kind === 'card');
                const wrongCount = catalog.filter((q) => q.last_correct === false).length;
                const rememberedCount = cards.filter((q) => q.rating === 'remembered').length;
                const label = (boot.profile_label || '学习档案').replace('本机学习档案', '学习档案');
                this.setData({
                    state: 'ready',
                    profileLabel: label,
                    identityNote: boot.identity_note || '',
                    attempts: stats.attempts,
                    correctRate: stats.attempts ? Math.round((stats.correct / stats.attempts) * 100) + '%' : '—',
                    rememberedCount: rememberedCount,
                    wrongCount: wrongCount,
                    cardCount: cards.length,
                    menuItems: [
                        {
                            key: 'wrong',
                            title: '我的错题',
                            desc: '回到不确定的知识点',
                            count: wrongCount + ' 道待巩固',
                        },
                        {
                            key: 'cards',
                            title: '我的知识卡',
                            desc: '翻卡回忆，记录自评',
                            count: cards.length + ' 张可学习',
                        },
                        {
                            key: 'records',
                            title: '学习记录',
                            desc: '查看历史，继续未完成练习',
                            count: stats.attempts + ' 次作答',
                        },
                    ],
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load(true);
    },

    handleMenuTap(event) {
        const key = event.currentTarget.dataset.key;
        if (key === 'wrong') {
            wx.switchTab({ url: '/pages/wrong/wrong' });
        } else if (key === 'cards') {
            wx.switchTab({ url: '/pages/cards/cards' });
        } else if (key === 'records') {
            wx.navigateTo({ url: '/pages/records/records' });
        }
    },
});
