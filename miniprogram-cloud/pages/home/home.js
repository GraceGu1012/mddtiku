const { api, ensureBoot } = require('../../utils/api');
const gamify = require('../../utils/gamify');

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
        // 游戏化头部
        level: 1,
        levelName: '见习学徒',
        xp: 0,
        todayXp: 0,
        streakDays: 0,
        levelProgress: 0,
        // 掌握度环
        masteryPercent: 0,
        ringStyle: '',
        mastered: 0,
        learning: 0,
        reviewCount: 0,
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
                const stats = progress.stats || { attempts: 0, correct: 0, today: 0 };
                const sessions = progress.sessions || [];
                const resume = sessions.filter((s) => s.answered < s.total)[0] || null;
                const g = dash.gamification || {};
                const lv = gamify.levelOf(g.xp || 0);
                const mastery = dash.mastery || {};
                const percent = mastery.percent || 0;
                this.setData({
                    state: 'ready',
                    today: stats.today,
                    attempts: stats.attempts,
                    correctRate: stats.attempts ? Math.round((stats.correct / stats.attempts) * 100) + '%' : '—',
                    wrongCount: catalog.filter((q) => q.last_correct === false).length,
                    questionCount: catalog.filter((q) => q.kind !== 'card').length,
                    cardCount: catalog.filter((q) => q.kind === 'card').length,
                    resume: resume,
                    level: lv.level,
                    levelName: g.level_name || lv.levelName,
                    xp: g.xp || 0,
                    todayXp: g.today_xp || 0,
                    streakDays: g.streak_days || 0,
                    levelProgress: lv.progress,
                    masteryPercent: percent,
                    mastered: mastery.mastered || 0,
                    learning: mastery.learning || 0,
                    reviewCount: mastery.review_count || 0,
                });
                this.drawRing(percent);
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    // 掌握度环：Canvas 2d 绘制，兼容所有基础库。
    drawRing(percent) {
        const query = wx.createSelectorQuery().in(this);
        query
            .select('#masteryRing')
            .fields({ node: true, size: true })
            .exec((res) => {
                if (!res || !res[0] || !res[0].node) {
                    return;
                }
                const canvas = res[0].node;
                const dpr = wx.getSystemInfoSync().pixelRatio || 2;
                canvas.width = res[0].width * dpr;
                canvas.height = res[0].height * dpr;
                const ctx = canvas.getContext('2d');
                ctx.scale(dpr, dpr);
                const cx = res[0].width / 2;
                const cy = res[0].height / 2;
                const radius = cx - 8;
                ctx.clearRect(0, 0, res[0].width, res[0].height);
                ctx.lineWidth = 12;
                ctx.lineCap = 'round';
                ctx.strokeStyle = '#F0EDF8';
                ctx.beginPath();
                ctx.arc(cx, cy, radius, 0, Math.PI * 2);
                ctx.stroke();
                if (percent > 0) {
                    ctx.strokeStyle = '#7C5CFC';
                    ctx.beginPath();
                    ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * percent) / 100);
                    ctx.stroke();
                }
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

    goExamPapers() {
        wx.navigateTo({ url: '/pages/exam-papers/exam-papers' });
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

    goReview() {
        // cards 是 tabBar 页面，navigateTo 无法打开；用 globalData 传递复习模式。
        getApp().globalData.reviewMode = true;
        wx.switchTab({ url: '/pages/cards/cards' });
    },

    goStructure() {
        wx.navigateTo({ url: '/pages/structure/structure' });
    },

    goLeaderboard() {
        wx.navigateTo({ url: '/pages/leaderboard/leaderboard' });
    },

    goAssistant() {
        wx.navigateTo({ url: '/pages/assistant/assistant' });
    },
});
