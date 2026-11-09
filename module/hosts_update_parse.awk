# UX02 small parser: input is untrusted hosts/domain data; output is canonical hosts/allow entries.
function domain_ok(d) {
    return d ~ /^[A-Za-z0-9][A-Za-z0-9_.-]*\.[A-Za-z0-9_.-]+$/ && d !~ /\.\./ && length(d) <= 253
}
function emit_domain(d, ip) {
    d=tolower(d)
    if (domain_ok(d) && d != "localhost" && d !~ /\.localhost$/) {
        if (mode=="allow") print d
        else print ip, d
        count++
    }
}
{
    sub(/\r$/, "", $0)
    sub(/#.*/, "", $0)
    if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^[[:space:]]*!/) next
    if ($0 ~ /^[[:space:]]*disabled\|/) next
    n=split($0, words, /[[:space:]]+/)
    if (n < 1) next
    first=words[1]
    if (mode=="hosts") {
        if (first ~ /^(0\.0\.0\.0|127\.0\.0\.1|::|::1)$/ || first ~ /^[0-9]+(\.[0-9]+){3}$/) {
            for (i=2;i<=n;i++) emit_domain(words[i], "0.0.0.0")
        } else if (domain_ok(first)) emit_domain(first, "0.0.0.0")
    } else if (mode=="allow") {
        if (first ~ /^[0-9.]+$/ || first ~ /^[0-9a-fA-F:]+$/) {
            for(i=2;i<=n;i++) emit_domain(words[i], "0.0.0.0")
        } else if (first ~ /^\*\./) {
            d=substr(first,3)
            if(domain_ok(d)) { print tolower(first); count++ }
        } else emit_domain(first,"0.0.0.0")
    } else if (mode=="custom") {
        if (first ~ /^[0-9.]+$/ || first ~ /^[0-9a-fA-F:]+$/) {
            for(i=2;i<=n;i++) emit_domain(words[i], first)
        }
    } else if (mode=="blacklist") {
        if(domain_ok(first)) emit_domain(first,"0.0.0.0")
    }
}
