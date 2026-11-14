const { api, ensureBoot, getBoot } = require('../../utils/api');
const gamify = require('../../utils/gamify');

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
        // 游戏化档案
        nickname: '',
        level: 1,
        levelName: '见习学徒',
        xp: 0,
        todayXp: 0,
        streakDays: 0,
        levelProgress: 0,
    },

    onShow() {
        this.load(this.data.state !== 'ready');
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => Promise.all([api('catalog'), api('progress'), api('dashboard')]))
            .then((results) => {
                const catalog = results[0];
                const progress = results[1];
                const dash = results[2] || {};
                const boot = getBoot() || {};
                const stats = progress.stats || { attempts: 0, correct: 0, today: 0 };
                const cards = catalog.filter((q) => q.kind === 'card');
                const wrongCount = catalog.filter((q) => q.last_correct === false).length;
                const rememberedCount = cards.filter((q) => q.rating === 'remembered').length;
                const label = (boot.profile_label || '学习档案').replace('本机学习档案', '学习档案');
                const g = dash.gamification || {};
                const lv = gamify.levelOf(g.xp || 0);
                this.setData({
                    state: 'ready',
                    profileLabel: label,
                    identityNote: boot.identity_note || '',
                    attempts: stats.attempts,
                    correctRate: stats.attempts ? Math.round((stats.correct / stats.attempts) * 100) + '%' : '—',
                    rememberedCount: rememberedCount,
                    wrongCount: wrongCount,
                    cardCount: cards.length,
                    nickname: g.nickname || '',
                    level: lv.level,
                    levelName: g.level_name || lv.levelName,
                    xp: g.xp || 0,
                    todayXp: g.today_xp || 0,
                    streakDays: g.streak_days || 0,
                    levelProgress: lv.progress,
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
                        {
                            key: 'leaderboard',
                            title: '学习排行榜',
                            desc: '周榜 / 月榜，看看谁的 XP 高',
                            count: 'Lv' + lv.level,
                        },
                        {
                            key: 'assistant',
                            title: '问一问墨督督',
                            desc: 'AI 学习助手，基于课程资料答疑',
                            count: '每天 20 次',
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
        } else if (key === 'leaderboard') {
            wx.navigateTo({ url: '/pages/leaderboard/leaderboard' });
        } else if (key === 'assistant') {
            wx.navigateTo({ url: '/pages/assistant/assistant' });
        }
    },

    goLeaderboard() {
        wx.navigateTo({ url: '/pages/leaderboard/leaderboard' });
    },
});
