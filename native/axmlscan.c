/*
 * SPDX-License-Identifier: MIT
 * TrackerGuard R1: bounded, dependency-free Android binary-XML manifest reader.
 * Does not load APK code; input must be an extracted AndroidManifest.xml.
 * Output: package|<package> and component|<type>|<class>|<enabled>.
 * Purposefully fail closed for unknown/unsupported AXML structures.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_FILE (16u * 1024u * 1024u)
#define MAX_STRINGS 250000u
#define MAX_COMPONENTS 12000u
#define MAX_NAME 1024u
#define NO_INDEX UINT32_MAX
#define XML_START 0x0102u
#define XML_END 0x0103u
#define XML_STRING_POOL 0x0001u
#define XML_RESOURCE_MAP 0x0180u
#define XML_NAMESPACE_START 0x0100u
#define XML_NAMESPACE_END 0x0101u

static unsigned char *buf;
static size_t len;
static size_t pool_off, pool_size, str_start;
static uint32_t strings_count, flags;
static int has_pool;
static char manifest_pkg[MAX_NAME];
static int seen_manifest;
struct component { char type[12]; char cls[MAX_NAME]; int enabled; };
static struct component *components;
static size_t count;

static void bad(const char *msg) { fprintf(stderr, "axmlscan: %s\n", msg); exit(2); }
static int within(size_t p, size_t n, size_t limit) { return p <= limit && n <= limit-p; }
static uint16_t u16(size_t p) {
    if (!within(p,2,len)) bad("truncated u16");
    return (uint16_t)(buf[p] | ((uint16_t)buf[p+1]<<8));
}
static uint32_t u32(size_t p) {
    if (!within(p,4,len)) bad("truncated u32");
    return (uint32_t)buf[p] | ((uint32_t)buf[p+1]<<8) |
           ((uint32_t)buf[p+2]<<16) | ((uint32_t)buf[p+3]<<24);
}
static int length8(size_t *p, size_t end, uint32_t *result) {
    if (!within(*p,1,end)) return 0;
    uint32_t a=buf[(*p)++];
    if (a&0x80u) { if (!within(*p,1,end)) return 0; *result=((a&0x7fu)<<8)|buf[(*p)++]; }
    else *result=a;
    return 1;
}
static int length16(size_t *p, size_t end, uint32_t *result) {
    if (!within(*p,2,end)) return 0;
    uint32_t a=u16(*p); *p+=2;
    if (a&0x8000u) { if (!within(*p,2,end)) return 0; *result=((a&0x7fffu)<<16)|u16(*p); *p+=2; }
    else *result=a;
    return 1;
}
static int getstr(uint32_t idx, char *out, size_t cap) {
    if (!has_pool || idx==NO_INDEX || idx>=strings_count || !cap) return 0;
    size_t pool_end=pool_off+pool_size;
    size_t offarr=pool_off+u16(pool_off+2);
    if (!within(offarr,(size_t)strings_count*4,pool_end)) return 0;
    uint32_t s_off=u32(offarr+(size_t)idx*4);
    if (s_off>pool_size || !within(pool_off+str_start,(size_t)s_off,pool_end)) return 0;
    size_t p=pool_off+str_start+s_off;
    uint32_t chars,bytes;
    if (flags&0x100u) {
        if (!length8(&p,pool_end,&chars) || !length8(&p,pool_end,&bytes)) return 0;
        if (bytes>=cap || !within(p,(size_t)bytes+1,pool_end) || buf[p+bytes]) return 0;
        for (uint32_t i=0;i<bytes;i++) if (buf[p+i]<0x20u || buf[p+i]>0x7eu) return 0;
        memcpy(out,buf+p,bytes); out[bytes]='\0';
    } else {
        if (!length16(&p,pool_end,&chars) || chars>=cap || !within(p,(size_t)chars*2+2,pool_end)) return 0;
        for (uint32_t i=0;i<chars;i++) {
            uint16_t c=u16(p+(size_t)i*2);
            if (c<0x20u || c>0x7eu) return 0;
            out[i]=(char)c;
        }
        if (u16(p+(size_t)chars*2)!=0) return 0;
        out[chars]='\0';
    }
    return 1;
}
static int getvalue(size_t attr, char *out, size_t cap) {
    uint32_t raw=u32(attr+8);
    if (raw!=NO_INDEX && getstr(raw,out,cap)) return 1;
    if (u16(attr+12)!=8u || buf[attr+15]!=3u) return 0;
    return getstr(u32(attr+16),out,cap);
}
static int get_attr(size_t chunk, size_t size, const char *key,
                    int android_ns, char *out, size_t cap, int *boolean) {
    if (size<36u) bad("short start-element chunk");
    uint16_t astart=u16(chunk+24), asize=u16(chunk+26), n=u16(chunk+28);
    if (asize<20u) bad("unsupported attribute size");
    size_t base=chunk+16u+astart;
    if (!within(base,(size_t)n*asize,chunk+size)) bad("attribute table out of bounds");
    for (uint16_t i=0;i<n;i++) {
        size_t at=base+(size_t)i*asize;
        char name[MAX_NAME], ns[MAX_NAME];
        if (!getstr(u32(at+4),name,sizeof name) || strcmp(name,key)) continue;
        uint32_t nsid=u32(at);
        if (android_ns) {
            if (!getstr(nsid,ns,sizeof ns) ||
                strcmp(ns,"http://schemas.android.com/apk/res/android")) continue;
        } else if (nsid!=NO_INDEX) continue;
        if (boolean && u16(at+12)==8u && buf[at+15]==0x12u) {
            *boolean=u32(at+16)!=0;
            return 1;
        }
        if (getvalue(at,out,cap)) {
            if (boolean) { if (!strcmp(out,"true")) *boolean=1;
                           else if (!strcmp(out,"false")) *boolean=0;
                           else return 0; }
            return 1;
        }
        return 0;
    }
    return 0;
}
static int validpkg(const char *p) {
    if (!p[0] || p[0]=='.') return 0;
    int dot=0;
    for (const char *c=p;*c;c++) {
        if (*c=='.') { if (c[1]=='.'||!c[1]) return 0; dot=1; }
        else if (!( (*c>='a'&&*c<='z') || (*c>='A'&&*c<='Z') ||
                    (*c>='0'&&*c<='9') || *c=='_' )) return 0;
    }
    return dot;
}
static int validclass(const char *p) {
    if (!p[0] || p[0]=='.' || strlen(p)>=MAX_NAME) return 0;
    for (const char *c=p;*c;c++) {
        if (!( (*c>='a'&&*c<='z') || (*c>='A'&&*c<='Z') ||
                (*c>='0'&&*c<='9') || *c=='_' || *c=='.' || *c=='$')) return 0;
        if (*c=='.' && (!c[1]||c[1]=='.')) return 0;
    }
    return strchr(p,'.')!=NULL;
}
static void add_component(const char *type,const char *name,int enabled) {
    if (count>=MAX_COMPONENTS) bad("too many components");
    struct component *c=&components[count];
    if (name[0]=='.') {
        if (snprintf(c->cls,sizeof c->cls,"%s%s",manifest_pkg,name)>=(int)sizeof c->cls) bad("class too long");
    } else if (!strchr(name,'.')) {
        if (snprintf(c->cls,sizeof c->cls,"%s.%s",manifest_pkg,name)>=(int)sizeof c->cls) bad("class too long");
    } else {
        if (strlen(name)>=sizeof c->cls) bad("class too long");
        strcpy(c->cls,name);
    }
    if (!validclass(c->cls)) bad("invalid component class");
    if (strlen(type)>=sizeof c->type) bad("invalid component kind");
    strcpy(c->type,type); c->enabled=enabled; count++;
}
static void parse(void) {
    if (len<8 || u16(0)!=3 || u16(2)!=8 || u32(4)!=len) bad("not Android binary XML");
    size_t p=8;
    int depth=0, application_depth=0;
    while (p<len) {
        if (!within(p,8,len)) bad("short XML chunk header");
        uint16_t type=u16(p), hdr=u16(p+2);
        uint32_t size=u32(p+4);
        if (hdr<8 || size<hdr || !within(p,size,len)) bad("invalid XML chunk bounds");
        if (type==XML_STRING_POOL) {
            if (has_pool || hdr<28 || size<28) bad("invalid string pool");
            strings_count=u32(p+8); flags=u32(p+16); str_start=u32(p+20);
            if (strings_count>MAX_STRINGS ||
                !within(p+hdr,(size_t)strings_count*4,p+size) ||
                str_start>size || str_start<hdr+(size_t)strings_count*4) bad("invalid string offsets");
            pool_off=p; pool_size=size; has_pool=1;
        } else if (type==XML_START) {
            if (!has_pool || hdr<16 || size<36) bad("invalid start element");
            depth++;
            char tag[MAX_NAME];
            if (!getstr(u32(p+20),tag,sizeof tag)) bad("invalid element name");
            if (!strcmp(tag,"manifest") && depth==1) {
                if (seen_manifest || !get_attr(p,size,"package",0,manifest_pkg,sizeof manifest_pkg,NULL) || !validpkg(manifest_pkg)) bad("invalid manifest package");
                seen_manifest=1;
            } else if (!strcmp(tag,"application") && depth==2 && seen_manifest) {
                application_depth=depth;
            } else if (application_depth==2 && depth==3) {
                const char *kind=NULL;
                if (!strcmp(tag,"activity") || !strcmp(tag,"activity-alias")) kind="activity";
                else if (!strcmp(tag,"service")) kind="service";
                else if (!strcmp(tag,"receiver")) kind="receiver";
                else if (!strcmp(tag,"provider")) kind="provider";
                if (kind) {
                    char name[MAX_NAME], btmp[16]={0}; int enabled=1;
                    if (!get_attr(p,size,"name",1,name,sizeof name,NULL)) bad("component missing android:name");
                    (void)get_attr(p,size,"enabled",1,btmp,sizeof btmp,&enabled);
                    add_component(kind,name,enabled);
                }
            }
        } else if (type==XML_END) {
            if (depth<1 || hdr<16 || size<24) bad("invalid end element");
            if (depth==application_depth) application_depth=0;
            depth--;
        } else if (type==XML_RESOURCE_MAP || type==XML_NAMESPACE_START || type==XML_NAMESPACE_END) {
            /* Valid but not needed to resolve android: attributes by namespace URI. */
        } else if (type==0x0104u) {
            /* XML CDATA (not expected in manifests, but harmless). */
        } else bad("unsupported XML chunk");
        p+=size;
    }
    if (!seen_manifest || depth!=0) bad("incomplete manifest structure");
}
int main(int argc,char **argv) {
    if (argc!=2) { fprintf(stderr,"Usage: axmlscan AndroidManifest.xml\n"); return 2; }
    FILE *f=fopen(argv[1],"rb"); if(!f) bad("cannot open manifest");
    if (fseek(f,0,SEEK_END)) bad("seek failed");
    long n=ftell(f); if (n<8 || n>(long)MAX_FILE) bad("manifest size refused");
    if (fseek(f,0,SEEK_SET)) bad("seek rewind failed");
    len=(size_t)n;
    buf=malloc(len); components=calloc(MAX_COMPONENTS,sizeof *components);
    if (!buf || !components) bad("out of memory");
    if (fread(buf,1,len,f)!=len) bad("failed to read manifest");
    fclose(f);
    parse();
    printf("package|%s\n",manifest_pkg);
    for(size_t i=0;i<count;i++)
        printf("component|%s|%s|%s\n",components[i].type,components[i].cls,
               components[i].enabled?"true":"false");
    free(buf);free(components);
    return 0;
}
