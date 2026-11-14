const KIND_NAMES = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    card: '知识卡',
};

const RATINGS = {
    again: '未记住',
    unsure: '有点模糊',
    remembered: '已记住',
};

function kindName(kind) {
    return KIND_NAMES[kind] || kind;
}

function ratingName(rating) {
    return RATINGS[rating] || '尚未学习';
}

function lastState(item) {
    if (item.last_correct === null || item.last_correct === undefined) {
        return '尚未练习';
    }
    return item.last_correct ? '最近答对' : '待巩固';
}

function pad(n) {
    return n < 10 ? '0' + n : '' + n;
}

function fmtTime(value) {
    if (!value) {
        return '';
    }
    const d = new Date(value);
    if (isNaN(d.getTime())) {
        return '';
    }
    return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function pills(item) {
    const list = [{ text: kindName(item.kind), blue: true }, { text: item.difficulty || '基础', blue: false }];
    const tags = Array.isArray(item.tags) ? item.tags : [];
    tags.forEach((t) => list.push({ text: t, blue: false }));
    return list;
}

function buildExplanation(solution) {
    const s = solution || {};
    const quality = s.learning_quality || null;
    const result = {
        inferred: s.answer_origin === 'ai_inference',
        sourceTitle: s.answer_origin === 'ai_inference' ? '题面 / 知识点来源（不是答案证据）' : '材料原文引用',
        evidences: (s.evidence || []).map((e) => ({
            label: e.label || e.start || e.source_id,
            quote: e.quote || '',
            sourceId: e.source_id || '',
        })),
        aiExplanation: s.ai_explanation || '暂无解析，请联系老师核对。',
        optionExplanations: (quality && quality.option_explanations ? quality.option_explanations : []).map((x) => ({
            letter: String.fromCharCode(65 + x.index),
            text: x.explanation,
        })),
        qualityOutline: '',
        qualityCoverage: '',
        misconceptionTitle: '',
        misconceptionSummary: '',
    };
    if (quality) {
        result.qualityOutline = quality.outline
            ? quality.outline.title || quality.outline.name || quality.outline.id || '大纲归属待核验'
            : '大纲归属待核验';
        const coverage = quality.coverage;
        if (coverage && coverage.status !== 'not_verified') {
            const years = Array.isArray(coverage.years) ? coverage.years.join('、') : '';
            result.qualityCoverage =
                (coverage.status === 'complete' ? '完整核验' : '部分核验') +
                '：' + coverage.question_count + ' 题，年份 ' + (years || '无') + '。';
        } else {
            result.qualityCoverage = '覆盖次数、年份待核验，不代表未考过。';
        }
        const misconception = quality.misconception;
        if (misconception && misconception.basis && misconception.basis !== 'none') {
            result.misconceptionTitle = misconception.basis === 'source_explicit' ? '材料指出的易错点' : '潜在混淆 · AI 生成';
            result.misconceptionSummary = misconception.summary || '';
        }
    }
    return result;
}

module.exports = {
    KIND_NAMES: KIND_NAMES,
    RATINGS: RATINGS,
    kindName: kindName,
    ratingName: ratingName,
    lastState: lastState,
    fmtTime: fmtTime,
    pills: pills,
    buildExplanation: buildExplanation,
};
