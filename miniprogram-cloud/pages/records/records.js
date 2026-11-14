const { api, ensureBoot, getBoot } = require('../../utils/api');
const common = require('../../utils/common');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        today: 0,
        attempts: 0,
        correctRate: '—',
        sessions: [],
        profileLabel: '',
        identityNote: '',
    },

    onShow() {
        this.load(this.data.state !== 'ready');
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => api('progress'))
            .then((progress) => {
                const boot = getBoot() || {};
                const stats = progress.stats || { attempts: 0, correct: 0, today: 0 };
                const sessions = (progress.sessions || []).map((s) => ({
                    id: s.id,
                    title: (s.mode === 'wrong' ? '错题巩固' : '课程练习') + ' · ' + s.total + ' 题',
                    detail: common.fmtTime(s.created_at) + ' · 已答 ' + s.answered + ' / ' + s.total + ' · 答对 ' + s.correct,
                    done: s.answered >= s.total,
                    actionText: s.answered < s.total ? '继续练习' : '查看记录',
                }));
                this.setData({
                    state: 'ready',
                    today: stats.today,
                    attempts: stats.attempts,
                    correctRate: stats.attempts ? Math.round((stats.correct / stats.attempts) * 100) + '%' : '—',
                    sessions: sessions,
                    profileLabel: boot.profile_label || '',
                    identityNote: boot.identity_note || '',
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load(true);
    },

    goSession(event) {
        const id = event.currentTarget.dataset.id;
        const done = event.currentTarget.dataset.done;
        const target = done ? '/pages/finish/finish?id=' : '/pages/exercise/exercise?id=';
        wx.navigateTo({ url: target + encodeURIComponent(id) });
    },

    goPractice() {
        wx.navigateTo({ url: '/pages/practice/practice' });
    },
});
