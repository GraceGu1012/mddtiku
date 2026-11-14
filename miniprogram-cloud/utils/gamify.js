// 与后端 learner.level_of 保持一致的等级换算（轻量镜像，避免额外请求）。
const LEVEL_NAMES = ['见习学徒', '初出茅庐', '勤学新秀', '知识行者', '题海健将', '百题斩将', '记忆大师', '学海宗师'];

function levelOf(xp) {
    let level = 1;
    while (xp >= 50 * level * (level + 1)) {
        level += 1;
    }
    const floor = 50 * (level - 1) * level;
    const ceiling = 50 * level * (level + 1);
    return {
        level: level,
        levelName: LEVEL_NAMES[Math.min(level - 1, LEVEL_NAMES.length - 1)],
        floor: floor,
        ceiling: ceiling,
        progress: ceiling > floor ? Math.min(100, Math.round(((xp - floor) / (ceiling - floor)) * 100)) : 100,
    };
}

module.exports = { levelOf: levelOf };
