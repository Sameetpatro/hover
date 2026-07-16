package store

import (
	"strconv"
	"strings"
)

// rebind converts ? placeholders to $1,$2,... for Postgres.
func rebind(postgres bool, q string) string {
	if !postgres {
		return q
	}
	var b strings.Builder
	n := 0
	for i := 0; i < len(q); i++ {
		if q[i] == '?' {
			n++
			b.WriteByte('$')
			b.WriteString(strconv.Itoa(n))
			continue
		}
		b.WriteByte(q[i])
	}
	return b.String()
}
