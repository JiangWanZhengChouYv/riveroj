#!/bin/sh

ROOT=/root/.hydro
ADDONS="$ROOT/addons"

# ---------------- 自动注册 addons/ 下的所有插件 ----------------
# 以前这里写死插件列表，每加一个插件都要改这个文件；
# 现在扫描 ADDONS 目录：凡是有 package.json 的子目录都注册。
# 纯 shell 实现（不依赖 python3/node），容器里一定能跑。
# 已有的其它条目（比如通过 npm 装的插件）会保留。
gen_addon_json() {
    _tmp="$ROOT/addon.json.tmp"
    _list="$ROOT/.addon-list"

    # 1. 固定 ui-default 在最前
    printf '@hydrooj/ui-default\n' > "$_list"

    # 2. 扫描本地插件（按名字排序，跳过隐藏目录、node_modules、以及没有 package.json 的）
    if [ -d "$ADDONS" ]; then
        for _d in "$ADDONS"/*; do
            [ -d "$_d" ] || continue
            _name=$(basename "$_d")
            case "$_name" in .*|node_modules) continue ;; esac
            [ -f "$_d/package.json" ] || continue
            printf '/root/.hydro/addons/%s\n' "$_name" >> "$_list"
        done
    fi

    # 3. 保留 addon.json 里原有的、不属于本地插件的条目
    if [ -f "$ROOT/addon.json" ]; then
        grep -o '"[^"]*"' "$ROOT/addon.json" 2>/dev/null \
            | tr -d '"' \
            | grep -v '^/root/\.hydro/addons/' \
            | grep -v '^@hydrooj/ui-default$' \
            | while IFS= read -r _e; do
                [ -n "$_e" ] && printf '%s\n' "$_e" >> "$_list"
            done
    fi

    # 4. 去重保序，拼成 JSON 数组
    awk '!seen[$0]++' "$_list" > "$_list.dedup" 2>/dev/null || cp "$_list" "$_list.dedup"
    {
        printf '['
        _first=1
        while IFS= read -r _e; do
            [ -z "$_e" ] && continue
            if [ "$_first" = "1" ]; then
                _first=0
            else
                printf ','
            fi
            printf '"%s"' "$_e"
        done < "$_list.dedup"
        printf ']\n'
    } > "$_tmp"

    mv "$_tmp" "$ROOT/addon.json"
    rm -f "$_list" "$_list.dedup"
    echo "addon.json: $(cat "$ROOT/addon.json")"
}

gen_addon_json

if [ ! -f "$ROOT/config.json" ]; then
    echo '{"host": "oj-mongo", "port": "27017", "name": "hydro", "username": "", "password": ""}' > "$ROOT/config.json"
fi

if [ ! -f "$ROOT/first" ]; then
    echo "for marking use only!" > "$ROOT/first"
    hydrooj cli user create Hydro@hydro.local hydro Hydro7890 1
    hydrooj cli user setPassword 1 Hydro7890
    hydrooj cli user setJudge 1
    hydrooj cli user create JWZCY@hydro.local JWZCY Hydro123 2
    hydrooj cli user setPassword 2 Hydro123
    hydrooj cli user setSuperAdmin 2
    hydrooj cli system set server.host 0.0.0.0
fi

pm2-runtime start hydrooj
