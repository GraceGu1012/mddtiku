const { api, ensureBoot } = require('../../utils/api');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        messages: [],
        input: '',
        sending: false,
        scrollTo: '',
    },

    onLoad() {
        ensureBoot()
            .then(() => {
                this.setData({
                    state: 'ready',
                    messages: [
                        {
                            id: 'welcome',
                            role: 'bot',
                            text: '你好，我是墨督督 🦉\n可以问我课程里学过的知识点，我会依据课程资料来回答。\n每天有 20 次提问机会。',
                        },
                    ],
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    onInput(event) {
        this.setData({ input: event.detail.value });
    },

    send() {
        const text = (this.data.input || '').trim();
        if (!text || this.data.sending) {
            return;
        }
        const messages = this.data.messages.concat([{ id: 'q' + Date.now(), role: 'me', text: text }]);
        this.setData({ messages: messages, input: '', sending: true, scrollTo: 'bottom' });
        api('ask', { question: text })
            .then((result) => {
                this.setData({
                    messages: this.data.messages.concat([
                        { id: 'a' + Date.now(), role: 'bot', text: result.answer },
                    ]),
                    sending: false,
                    scrollTo: 'bottom',
                });
            })
            .catch((err) => {
                this.setData({
                    messages: this.data.messages.concat([
                        { id: 'e' + Date.now(), role: 'bot', text: '抱歉出了点问题：' + err.message },
                    ]),
                    sending: false,
                    scrollTo: 'bottom',
                });
            });
    },
});
