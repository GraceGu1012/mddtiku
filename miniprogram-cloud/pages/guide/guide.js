const SLIDES = [
    {
        emoji: '🦉',
        title: '你好，我是墨督督',
        desc: '一位住在题库里的小猫头鹰，帮你把学过的知识真正记住。',
    },
    {
        emoji: '🎯',
        title: '练 · 有依据',
        desc: '每道题都来自老师审核过的课程资料，答完可以回到原文出处。',
    },
    {
        emoji: '🔥',
        title: '坚持 · 有回报',
        desc: '答对得 XP，卡片记住涨等级，连胜打卡上排行榜。',
    },
];

Page({
    data: {
        slides: SLIDES,
        current: 0,
    },

    onChange(event) {
        this.setData({ current: event.detail.current });
    },

    finish() {
        wx.setStorageSync('mdd_guide_seen_v1', Date.now());
        wx.reLaunch({ url: '/pages/home/home' });
    },
});
