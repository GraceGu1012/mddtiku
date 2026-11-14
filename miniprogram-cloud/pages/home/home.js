const { api, ensureBoot } = require('../../utils/api');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        today: 0,
        attempts: 0,
        correctRate: '—',
        wrongCount: 0,
        questionCount: 0,
        cardCount: 0,
        resume: null,
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
                const stats = progress.stats || { attempts: 0, correct: 0, today: 0 };
                const sessions = progress.sessions || [];
                const resume = sessions.filter((s) => s.answered < s.total)[0] || null;
                this.setData({
                    state: 'ready',
                    today: stats.today,
                    attempts: stats.attempts,
                    correctRate: stats.attempts ? Math.round((stats.correct / stats.attempts) * 100) + '%' : '—',
                    wrongCount: catalog.filter((q) => q.last_correct === false).length,
                    questionCount: catalog.filter((q) => q.kind !== 'card').length,
                    cardCount: catalog.filter((q) => q.kind === 'card').length,
                    resume: resume,
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load(true);
    },

    goPrimary() {
        const resume = this.data.resume;
        if (resume) {
            wx.navigateTo({ url: '/pages/exercise/exercise?id=' + encodeURIComponent(resume.id) });
        } else {
            wx.navigateTo({ url: '/pages/practice/practice' });
        }
    },

    goPractice() {
        wx.navigateTo({ url: '/pages/practice/practice' });
    },

    goWrong() {
        wx.switchTab({ url: '/pages/wrong/wrong' });
    },

    goCards() {
        wx.switchTab({ url: '/pages/cards/cards' });
    },
});
