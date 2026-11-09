// UX04: loopback-only HTTP blocked-image responder. No TLS, proxying, or telemetry.
#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif
static volatile sig_atomic_t running=1;
static void stop(int sig) { (void)sig; running=0; }
static const unsigned char gif[] = {
  0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,
  0x80,0x00,0x00,0xff,0xff,0xff,0xff,0xff,0xff,0x21,
  0xf9,0x04,0x01,0x00,0x00,0x00,0x00,0x2c,0x00,0x00,
  0x00,0x00,0x01,0x00,0x01,0x00,0x00,0x02,0x02,0x44,
  0x01,0x00,0x3b
};
static const char logo[] =
  "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"240\" height=\"80\" viewBox=\"0 0 240 80\">"
  "<rect width=\"240\" height=\"80\" rx=\"14\" fill=\"#1d2637\"/>"
  "<path d=\"M41 12L63 22V42C63 56 53 67 41 71C29 67 19 56 19 42V22Z\" fill=\"#70d3a5\"/>"
  "<path d=\"M32 41L39 48L51 34\" fill=\"none\" stroke=\"#162b25\" stroke-width=\"5\"/>"
  "<text x=\"75\" y=\"36\" fill=\"#fff\" font-size=\"18\" font-family=\"sans-serif\">bindhosts</text>"
  "<text x=\"75\" y=\"56\" fill=\"#b5c7d4\" font-size=\"11\" font-family=\"sans-serif\">Content blocked</text></svg>";
static int write_all(int fd,const void *buf,size_t len) {
  const unsigned char *p=(const unsigned char*)buf;
  while(len) { ssize_t n=send(fd,p,len,MSG_NOSIGNAL); if(n<=0) return -1; p+=(size_t)n;len-=(size_t)n; }
  return 0;
}
static int parse_port(const char *arg) {
  char *end=NULL;
  long port=strtol(arg,&end,10);
  if(!arg[0] || !end || *end || port<1 || port>65535) return -1;
  return (int)port;
}
static int addr_of(struct sockaddr_in *addr,int port) {
  memset(addr,0,sizeof(*addr));addr->sin_family=AF_INET;
  addr->sin_port=htons((uint16_t)port);
  return inet_pton(AF_INET,"127.0.0.1",&addr->sin_addr)==1 ? 0:-1;
}
static int probe(int port,int is_logo) {
  struct sockaddr_in addr;
  if(addr_of(&addr,port))return 3;
  int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return 3;
  struct timeval tv={2,0};
  setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof(tv));
  setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof(tv));
  int ok=0;
  if(connect(fd,(struct sockaddr*)&addr,sizeof(addr))==0) {
    const char req[]="GET / HTTP/1.0\r\nHost: probe.invalid\r\n\r\n";
    if(write_all(fd,req,sizeof(req)-1)==0) {
      char buf[1024];ssize_t len=recv(fd,buf,sizeof(buf)-1,0);
      if(len>0) {buf[len]=0; ok=strstr(buf,"X-Bindhosts-Response: UX04")!=NULL && strstr(buf, is_logo?"X-Bindhosts-Mode: logo":"X-Bindhosts-Mode: transparent")!=NULL;}
    }
  }
  close(fd);return ok?0:3;
}
static void reply(int fd,int is_logo) {
  char buf[2048];
  ssize_t n=recv(fd,buf,sizeof(buf)-1,0);if(n<=0)return;
  buf[n]=0;
  if(strncmp(buf,"GET ",4)!=0 && strncmp(buf,"HEAD ",5)!=0) return;
  int is_head=strncmp(buf,"HEAD ",5)==0;
  const void *body=is_logo?(const void*)logo:(const void*)gif;
  size_t sz=is_logo?sizeof(logo)-1:sizeof(gif);
  char hdr[320];
  int hn=snprintf(hdr,sizeof(hdr),
    "HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %zu\r\n"
    "Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
    "X-Bindhosts-Response: UX04\r\nX-Bindhosts-Mode: %s\r\nConnection: close\r\n\r\n",
    is_logo?"image/svg+xml":"image/gif",sz,is_logo?"logo":"transparent");
  if(hn<0 || (size_t)hn>=sizeof(hdr))return;
  if(write_all(fd,hdr,(size_t)hn)==0 && !is_head) (void)write_all(fd,body,sz);
}
int main(int argc,char **argv) {
  int port=80;int is_logo=0;int do_probe=0;
  for(int i=1;i<argc;i++) {
    if(strcmp(argv[i],"--mode")==0 && i+1<argc) {
      const char *m=argv[++i];
      if(strcmp(m,"logo")==0)is_logo=1;
      else if(strcmp(m,"transparent")==0)is_logo=0;
      else return 2;
    } else if(strcmp(argv[i],"--port")==0 && i+1<argc) {
      port=parse_port(argv[++i]);if(port<0)return 2;
    } else if(strcmp(argv[i],"--probe")==0)do_probe=1;
    else return 2;
  }
  if(do_probe)return probe(port,is_logo);
  struct sockaddr_in addr;if(addr_of(&addr,port))return 2;
  int listener=socket(AF_INET,SOCK_STREAM,0);if(listener<0)return 1;
  int yes=1;setsockopt(listener,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
  if(bind(listener,(struct sockaddr*)&addr,sizeof(addr))!=0 || listen(listener,16)!=0) {close(listener);return 1;}
  // Explicitly avoid SA_RESTART: SIGTERM must interrupt accept(), otherwise
  // a daemon with no pending connections can remain alive after stop request.
  struct sigaction action;
  memset(&action,0,sizeof(action));
  action.sa_handler=stop;
  sigemptyset(&action.sa_mask);
  action.sa_flags=0;
  if(sigaction(SIGTERM,&action,NULL)!=0 || sigaction(SIGINT,&action,NULL)!=0) {
    close(listener);return 1;
  }
  signal(SIGPIPE,SIG_IGN);
  while(running) {
    int client=accept(listener,NULL,NULL);
    if(client<0) {if(errno==EINTR)continue;break;}
    struct timeval tv={2,0};setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof(tv));
    setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof(tv));
    reply(client,is_logo);close(client);
  }
  close(listener);return 0;
}
