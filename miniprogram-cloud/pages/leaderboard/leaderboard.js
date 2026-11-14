const { api, ensureBoot } = require('../../utils/api');
const gamify = require('../../utils/gamify');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        period: 'week',
        entries: [],
        me: null,
        myLevel: 1,
        myLevelName: '',
        myProgress: 0,
    },

    onLoad(options) {
        if (options && options.period === 'month') {
            this.setData({ period: 'month' });
        }
    },

    onShow() {
        this.load(this.data.state !== 'ready');
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => api('leaderboard?period=' + this.data.period))
            .then((data) => {
                const me = data.me || null;
                const lv = gamify.levelOf(me ? me.xp : 0);
                this.setData({
                    state: 'ready',
                    entries: (data.entries || []).map((e) => ({
                        rank: e.rank,
                        nickname: e.nickname || '神秘学员',
                        xp: e.xp,
                        isMe: e.is_me,
                        medal: e.rank === 1 ? '👑' : e.rank === 2 ? '🥈' : e.rank === 3 ? '🥉' : '',
                    })),
                    me: me,
                    myLevel: lv.level,
                    myLevelName: lv.levelName,
                    myProgress: lv.progress,
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load(true);
    },

    switchPeriod(event) {
        const period = event.currentTarget.dataset.period;
        if (period !== this.data.period) {
            this.setData({ period: period });
            this.load(true);
        }
    },
});
