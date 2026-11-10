// SPDX-License-Identifier: MIT
// UX07: opt-in localhost HTTPS blocked-image responder, no forwarding or request logs.
// All certificates are minted on the device. The CA private key never leaves private storage.
package main

import (
	"bufio"
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

const marker = "# bh-response"
const gif = "GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
const logo = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="80" viewBox="0 0 240 80"><rect width="240" height="80" rx="14" fill="#1d2637"/><path d="M41 12L63 22V42C63 56 53 67 41 71C29 67 19 56 19 42V22Z" fill="#70d3a5"/><path d="M32 41L39 48L51 34" fill="none" stroke="#162b25" stroke-width="5"/><text x="75" y="36" fill="#fff" font-size="18" font-family="sans-serif">bindhosts</text><text x="75" y="56" fill="#b5c7d4" font-size="11" font-family="sans-serif">Content blocked</text></svg>`

func validDNS(s string) bool {
	if s == "localhost" {
		return true
	}
	if len(s) > 253 || len(s) < 4 || s != strings.ToLower(s) || !strings.Contains(s, ".") || strings.HasSuffix(s, ".") {
		return false
	}
	for _, label := range strings.Split(s, ".") {
		if len(label) < 1 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, c := range label {
			if !(c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '-') {
				return false
			}
		}
	}
	return true
}
func keyFor(s string) [16]byte {
	sum := sha256.Sum256([]byte(s))
	var k [16]byte
	copy(k[:], sum[:16])
	return k
}
func secureState(dir string) error {
	parent := filepath.Dir(dir)
	if p, e := os.Lstat(parent); e != nil || !p.IsDir() || p.Mode()&os.ModeSymlink != 0 {
		return errors.New("private parent unavailable")
	}
	if e := os.Mkdir(dir, 0700); e != nil && !os.IsExist(e) {
		return e
	}
	st, e := os.Lstat(dir)
	if e != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return errors.New("private TLS directory unsafe")
	}
	return os.Chmod(dir, 0700)
}
func readPrivate(path string) ([]byte, error) {
	st, e := os.Lstat(path)
	if e != nil {
		return nil, e
	}
	if !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 {
		return nil, errors.New("unsafe certificate/key permissions")
	}
	return os.ReadFile(path)
}
func writeExclusive(path string, raw []byte) error {
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	if _, e = f.Write(raw); e != nil {
		f.Close()
		os.Remove(path)
		return e
	}
	if e = f.Sync(); e != nil {
		f.Close()
		os.Remove(path)
		return e
	}
	if e = f.Close(); e != nil {
		os.Remove(path)
		return e
	}
	return nil
}

// Export is a public certificate only; O_EXCL prevents overwriting an existing
// or symlink destination even if shared Downloads changes between checks.
func exportPublicCA(dir, dest string) error {
	fp, e := fingerprint(dir)
	if e != nil {
		return e
	}
	short := fp[:16]
	if !filepath.IsAbs(dest) || filepath.Base(dest) != "bindhosts-local-ca-"+short+".crt" {
		return errors.New("invalid certificate export destination")
	}
	parent := filepath.Dir(dest)
	st, e := os.Lstat(parent)
	if e != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return errors.New("unsafe export directory")
	}
	cert, _ := caPaths(dir)
	data, e := readPrivate(cert)
	if e != nil {
		return e
	}
	f, e := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if e != nil {
		return e
	}
	if _, e = f.Write(data); e != nil {
		f.Close()
		os.Remove(dest)
		return e
	}
	if e = f.Sync(); e != nil {
		f.Close()
		os.Remove(dest)
		return e
	}
	if e = f.Close(); e != nil {
		os.Remove(dest)
		return e
	}
	return nil
}

func caPaths(dir string) (string, string) {
	return filepath.Join(dir, "ca.crt"), filepath.Join(dir, "ca.key")
}
func pemKey(k *ecdsa.PrivateKey) ([]byte, error) {
	raw, e := x509.MarshalECPrivateKey(k)
	if e != nil {
		return nil, e
	}
	return pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: raw}), nil
}
func genCA(dir string) error {
	if e := secureState(dir); e != nil {
		return e
	}
	cert, key := caPaths(dir)
	if _, e := os.Lstat(cert); e == nil {
		return errors.New("certificate already exists (no overwrite)")
	} else if !os.IsNotExist(e) {
		return e
	}
	if _, e := os.Lstat(key); e == nil {
		return errors.New("key already exists (no overwrite)")
	} else if !os.IsNotExist(e) {
		return e
	}
	k, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if e != nil {
		return e
	}
	serial, e := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if e != nil {
		return e
	}
	now := time.Now()
	tpl := &x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: "bindhosts local blocked-page CA"}, NotBefore: now.Add(-time.Hour), NotAfter: now.AddDate(2, 0, 0), IsCA: true, BasicConstraintsValid: true, MaxPathLen: 0, MaxPathLenZero: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageCRLSign}
	der, e := x509.CreateCertificate(rand.Reader, tpl, tpl, &k.PublicKey, k)
	if e != nil {
		return e
	}
	keyraw, e := pemKey(k)
	if e != nil {
		return e
	}
	// Never publish an incomplete CA pair as usable; cleanup on partial failure.
	if e = writeExclusive(key, keyraw); e != nil {
		return e
	}
	if e = writeExclusive(cert, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})); e != nil {
		os.Remove(key)
		return e
	}
	return nil
}
func readCA(dir string) (*x509.Certificate, *ecdsa.PrivateKey, error) {
	cert, key := caPaths(dir)
	raw, e := readPrivate(cert)
	if e != nil {
		return nil, nil, e
	}
	b, _ := pem.Decode(raw)
	if b == nil || b.Type != "CERTIFICATE" {
		return nil, nil, errors.New("invalid CA cert")
	}
	ca, e := x509.ParseCertificate(b.Bytes)
	if e != nil {
		return nil, nil, e
	}
	if !ca.IsCA || ca.KeyUsage&x509.KeyUsageCertSign == 0 || time.Now().After(ca.NotAfter) {
		return nil, nil, errors.New("unusable CA")
	}
	keyraw, e := readPrivate(key)
	if e != nil {
		return nil, nil, e
	}
	kb, _ := pem.Decode(keyraw)
	if kb == nil || kb.Type != "EC PRIVATE KEY" {
		return nil, nil, errors.New("invalid CA key")
	}
	k, e := x509.ParseECPrivateKey(kb.Bytes)
	if e != nil {
		return nil, nil, e
	}
	pub, ok := ca.PublicKey.(*ecdsa.PublicKey)
	if !ok || !pub.Equal(&k.PublicKey) {
		return nil, nil, errors.New("CA key mismatch")
	}
	return ca, k, nil
}
func fingerprint(dir string) (string, error) {
	ca, _, e := readCA(dir)
	if e != nil {
		return "", e
	}
	sum := sha256.Sum256(ca.Raw)
	return strings.ToUpper(hex.EncodeToString(sum[:])), nil
}

// Only exactly managed loopback records are eligible for SNI signing. This list
// is not a general CA proxy: unblocked hosts never get a certificate.
type allowedHosts struct {
	mu      sync.Mutex
	path    string
	next    time.Time
	allowed map[[16]byte]struct{}
}

func (a *allowedHosts) permits(host string) bool {
	if host == "localhost" {
		return true
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if time.Now().After(a.next) {
		a.next = time.Now().Add(10 * time.Second)
		next := make(map[[16]byte]struct{})
		f, e := os.Open(a.path)
		if e == nil {
			reader := bufio.NewScanner(f)
			reader.Buffer(make([]byte, 0, 65536), 1024*1024)
			for reader.Scan() {
				line := reader.Text()
				if !strings.HasPrefix(line, "127.0.0.1 ") {
					continue
				}
				fields := strings.Fields(line)
				if len(fields) == 4 && fields[0] == "127.0.0.1" && fields[2] == "#" && fields[3] == "bh-response" && validDNS(fields[1]) {
					next[keyFor(fields[1])] = struct{}{}
				}
			}
			if reader.Err() == nil {
				a.allowed = next
			} else {
				a.allowed = nil
			}
			f.Close()
		} else {
			a.allowed = nil
		}
	}
	_, ok := a.allowed[keyFor(host)]
	return ok
}

type certResolver struct {
	mu      sync.Mutex
	ca      *x509.Certificate
	key     *ecdsa.PrivateKey
	cache   map[string]*tls.Certificate
	allowed *allowedHosts
}

func (r *certResolver) get(hello *tls.ClientHelloInfo) (*tls.Certificate, error) {
	name := strings.ToLower(strings.TrimSuffix(hello.ServerName, "."))
	if !validDNS(name) || !r.allowed.permits(name) {
		return nil, errors.New("SNI not in managed blocklist")
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if saved := r.cache[name]; saved != nil && saved.Leaf != nil && time.Until(saved.Leaf.NotAfter) > time.Hour {
		return saved, nil
	}
	k, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if e != nil {
		return nil, e
	}
	serial, e := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if e != nil {
		return nil, e
	}
	now := time.Now()
	cert := &x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: name}, DNSNames: []string{name}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(48 * time.Hour), BasicConstraintsValid: true, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, e := x509.CreateCertificate(rand.Reader, cert, r.ca, &k.PublicKey, r.key)
	if e != nil {
		return nil, e
	}
	parsed, e := x509.ParseCertificate(der)
	if e != nil {
		return nil, e
	}
	pair := &tls.Certificate{Certificate: [][]byte{der, r.ca.Raw}, PrivateKey: k, Leaf: parsed}
	if len(r.cache) >= 96 {
		r.cache = make(map[string]*tls.Certificate)
	}
	r.cache[name] = pair
	return pair, nil
}
func serve(dir, hosts, mode string, port int) error {
	if mode != "logo" && mode != "transparent" {
		return errors.New("invalid response mode")
	}
	ca, key, e := readCA(dir)
	if e != nil {
		return e
	}
	l, e := net.Listen("tcp4", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)))
	if e != nil {
		return e
	}
	defer l.Close()
	resolver := &certResolver{ca: ca, key: key, cache: make(map[string]*tls.Certificate), allowed: &allowedHosts{path: hosts}}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Never forward cookies, body, headers or the original request anywhere.
		if r.Method != "GET" && r.Method != "HEAD" {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if r.TLS == nil || r.TLS.ServerName == "" {
			w.WriteHeader(http.StatusMisdirectedRequest)
			return
		}
		host := strings.ToLower(strings.Split(r.Host, ":")[0])
		if host != strings.ToLower(r.TLS.ServerName) {
			w.WriteHeader(http.StatusMisdirectedRequest)
			return
		}
		body, mime := []byte(gif), "image/gif"
		if mode == "logo" {
			body, mime = []byte(logo), "image/svg+xml"
		}
		w.Header().Set("Content-Type", mime)
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Bindhosts-TLS", "UX07")
		w.Header().Set("X-Bindhosts-Mode", mode)
		w.Header().Set("Content-Length", strconv.Itoa(len(body)))
		w.WriteHeader(http.StatusOK)
		if r.Method == "GET" {
			_, _ = w.Write(body)
		}
	})
	server := &http.Server{Handler: handler, ReadHeaderTimeout: 3 * time.Second, ReadTimeout: 5 * time.Second, WriteTimeout: 5 * time.Second, IdleTimeout: 4 * time.Second, MaxHeaderBytes: 4096, ErrorLog: log.New(io.Discard, "", 0), TLSNextProto: map[string]func(*http.Server, *tls.Conn, http.Handler){}}
	tlsListener := tls.NewListener(l, &tls.Config{MinVersion: tls.VersionTLS12, GetCertificate: resolver.get})
	return server.Serve(tlsListener)
}
func probe(dir, mode string, port int) error {
	raw, e := readPrivate(filepath.Join(dir, "ca.crt"))
	if e != nil {
		return e
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(raw) {
		return errors.New("CA unreadable")
	}
	dialer := &net.Dialer{Timeout: 2 * time.Second}
	conn, e := tls.DialWithDialer(dialer, "tcp4", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), &tls.Config{RootCAs: pool, ServerName: "localhost", MinVersion: tls.VersionTLS12})
	if e != nil {
		return e
	}
	defer conn.Close()
	if _, e = io.WriteString(conn, "GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"); e != nil {
		return e
	}
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	data, e := io.ReadAll(io.LimitReader(conn, 8192))
	if e != nil {
		return e
	}
	if !bytes.Contains(data, []byte("X-Bindhosts-Tls: UX07")) && !bytes.Contains(data, []byte("X-Bindhosts-TLS: UX07")) {
		return errors.New("responder identity check failed")
	}
	if !bytes.Contains(data, []byte("X-Bindhosts-Mode: "+mode)) {
		return errors.New("mode mismatch")
	}
	return nil
}
func main() {
	action := flag.String("action", "", "cert-create|cert-status|cert-export|serve|probe")
	state := flag.String("state", "", "private TLS directory")
	hosts := flag.String("hosts", "", "managed hosts file")
	dest := flag.String("dest", "", "public CA certificate export path")
	mode := flag.String("mode", "logo", "logo|transparent")
	port := flag.Int("port", 443, "local TCP port")
	flag.Parse()
	if *state == "" || *port <= 0 || *port > 65535 || flag.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "BH_HTTPS_ERROR: invalid arguments")
		os.Exit(2)
	}
	var e error
	switch *action {
	case "cert-create":
		e = genCA(*state)
		if e == nil {
			fmt.Println("BH_HTTPS_CERT_CREATED")
		}
	case "cert-status":
		var fp string
		fp, e = fingerprint(*state)
		if e == nil {
			fmt.Println("fingerprint_sha256=" + fp)
		}
	case "cert-export":
		if *dest == "" {
			e = errors.New("export destination required")
		} else {
			e = exportPublicCA(*state, *dest)
		}
		if e == nil {
			fmt.Println("BH_HTTPS_PUBLIC_CA_EXPORT_PASS")
		}
	case "serve":
		if *hosts == "" {
			e = errors.New("hosts path required")
		} else {
			e = serve(*state, *hosts, *mode, *port)
		}
	case "probe":
		e = probe(*state, *mode, *port)
		if e == nil {
			fmt.Println("BH_HTTPS_LOCAL_TLS_PASS (Android trust not tested)")
		}
	default:
		e = errors.New("unknown action")
	}
	if e != nil {
		fmt.Fprintln(os.Stderr, "BH_HTTPS_ERROR:", e)
		os.Exit(1)
	}
}
