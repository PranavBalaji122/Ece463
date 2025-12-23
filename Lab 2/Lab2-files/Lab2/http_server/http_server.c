//

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <signal.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <netdb.h>
#include <arpa/inet.h>

#define LISTEN_QUEUE 50 /* Max timeout */
#define RECV_TIMEOUT_SEC 5
#define MAX_REQ_LINE 4096

#define DBADDR "127.0.0.1"
#define UDP_CHUNK 4096  // udp chunk size from db_server
#define DB_ADDR   "127.0.0.1" // adress of db server

// function definitions 

int makeTheListenSocket(uint16_t port);
void recvTimeout(int sockfd, int timeout_sec);
ssize_t recv_line(int sockfd, char *buf, size_t bufsize);
void printOutRequest(const char *ip, const char *reqline, const char *status);
int sendHTML(int sockfd, const char *status_line, const char *title);
int bad_uri(const char *uri);
int mapToPath(const char *uri, char *path, size_t pathsize);
const char *guess_mime(const char *path);
static int sendAll(int sockfd, const void *buf, size_t len);


// URL-decode in place: converts %XX and '+'
static int url_decode_inplace(char *s) {
    char *r = s;
    char *w =s;
    while (*r) {
        if (*r == '+') {
            *w++ = ' ';
            r++;
        } else if (*r == '%' && r[1] && r[2]) {
            int hi;
            int lo;
            char h = r[1], l = r[2];
            if ('0'<=h && h<='9') hi = h-'0';
            else if ('A'<=h && h<='F') hi = 10 + (h-'A');
            else if ('a'<=h && h<='f') hi = 10 + (h-'a');
            else return -1;
            if ('0'<=l && l<='9') lo = l-'0';
            else if ('A'<=l && l<='F') lo = 10 + (l-'A');
            else if ('a'<=l && l<='f') lo = 10 + (l-'a');
            else return -1;
            *w++ = (char)((hi<<4) | lo);
            r += 3;
        } else {
            *w++ = *r++;
        }
    }
    *w = '\0';
    return 0;
}

// string the jpg extentions for the http reuqest 
static void strip_dot_jpg(char *s) {
    // geting the len 
    size_t len = strlen(s);
    
    /// checking if the string >=4
    if (len >= 4) {
        const char *tail = s + len - 4;
        if (tail[0]=='.' &&
            (tail[1]=='j'||tail[1]=='J') &&
            (tail[2]=='p'||tail[2]=='P') &&
            (tail[3]=='g'||tail[3]=='G')) {
            s[len-4] = '\0';
        }
    }

}


static const char* get_qparam(const char *uri, const char *key, char *out, size_t cap) {
    const char *questionMark = strchr(uri, '?');
    if (!questionMark){
        return NULL;
    } 
    questionMark++; // move past the queetion mark
    size_t klen = strlen(key);


    const char *p = questionMark;
    
    while (*p) {
        if (!strncmp(p, key, klen) && p[klen] == '=') {
            p += klen + 1;
            size_t i = 0;
            while (*p && *p != '&' && i + 1 < cap) {
                out[i++] = *p++;
            }
            out[i] = '\0';
            return out;
        }


        while (*p && *p != '&') p++;
        if (*p == '&') p++;
    }

    return NULL;
}

// fetching the data from the db_server via the udp protocol
static int udp_fetch_file(uint16_t dbport, const char *name, unsigned char **out, size_t *outlen) {
    *out = NULL; *outlen = 0;

    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return -1;

    struct timeval tv = { .tv_sec = 2, .tv_usec = 0 };
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    // settting up the socket
    struct sockaddr_in db; memset(&db, 0, sizeof(db));
    db.sin_family = AF_INET;
    db.sin_port   = htons(dbport);
    inet_pton(AF_INET, DB_ADDR, &db.sin_addr);

    // send filename
    if (sendto(s, name, strlen(name), 0, (struct sockaddr*)&db, sizeof(db)) < 0) {
        close(s); return -1;
    }

    // get the chenks 
    size_t cap = 8192, len = 0;
    unsigned char *buf = malloc(cap);
    if (!buf) { close(s); return -1; }


    for (;;) {
        unsigned char pkt[UDP_CHUNK];
        socklen_t alen = sizeof(db);
        ssize_t n = recvfrom(s, pkt, sizeof(pkt), 0, (struct sockaddr*)&db, &alen);
        if (n < 0) { free(buf); close(s); return -1; }

        // control messages from db_server.c
        if (n == 4 && memcmp(pkt, "DONE", 4) == 0) {
            break;
        }
        if (n >= 14 && memcmp(pkt, "File Not Found", 14) == 0) {
            free(buf); close(s); return -2; // not found
        }

        if (len + (size_t)n > cap) {
            size_t newcap = cap * 2;
            if (newcap < len + (size_t)n) newcap = len + (size_t)n;
            unsigned char *nb = realloc(buf, newcap);
            if (!nb) { free(buf); close(s); return -1; }
            buf = nb; cap = newcap;
        }
        memcpy(buf + len, pkt, (size_t)n);
        len += (size_t)n;
    }

    close(s);
    *out = buf; *outlen = len;
    return 0;
}

static int sendAll(int sockfd, const void *buf, size_t len) {
    const char *p = (const char*)buf;
    size_t left = len;
    while (left > 0) {
        ssize_t n = send(sockfd, p, left, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        p += n;
        left -= (size_t)n;
    }
    return 0;
}

int makeTheListenSocket(uint16_t port) {
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) { perror("socket"); exit(1); }

    int yes = 1;
    if (setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes)) < 0) {
        perror("setsockopt"); exit(1);
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    
    addr.sin_port        = htons(port);

    if (bind(s, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("bind"); exit(1);
    }


    if (listen(s, LISTEN_QUEUE) < 0) {
        perror("listen"); exit(1);
    }


    return s;
}

void recvTimeout(int sockfd, int timeout_sec) {
    struct timeval tv;
    tv.tv_sec  = timeout_sec;
    tv.tv_usec = 0;
    (void)setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
}

// read one CRLF-terminated line (like Lab1 style), capped by bufsize
ssize_t recv_line(int sockfd, char *buf, size_t bufsize) {
    size_t i = 0;
    while (i + 1 < bufsize) {
        char c;
        ssize_t n = recv(sockfd, &c, 1, 0);
        if (n == 0) break;                // peer closed
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;                    // error/timeout
        }
        buf[i++] = c;
        if (i >= 2 && buf[i-2] == '\r' && buf[i-1] == '\n') {
            buf[i] = '\0';
            return (ssize_t)i;


        }
    }
    buf[i] = '\0';
    return (ssize_t)i;
}

void printOutRequest(const char *ip, const char *reqline, const char *status) {

    // printing in the correct way 
    printf("%s \"%s\" %s\n", ip, reqline, status);
    fflush(stdout);
}

int sendHTML(int sockfd, const char *status_line, const char *title) {
    char body[256];
    int blen = snprintf(body, sizeof(body),
        "<html><body><h1>%s</h1></body></html>", title);
    if (blen < 0) return -1;

    char hdr[256];
    int hlen = snprintf(hdr, sizeof(hdr),
        "HTTP/1.0 %s\r\n"
        "Content-Length: %d\r\n"
        "Content-Type: text/html\r\n"
        "\r\n", status_line, blen);
    if (hlen < 0) return -1;

    if (sendAll(sockfd, hdr, (size_t)hlen) < 0) return -1;
    if (sendAll(sockfd, body, (size_t)blen) < 0) return -1;
    return 0;
}

// 1 isbad, 0 is ok
int bad_uri(const char *uri) {
    if (uri[0] != '/') return 1;
    if (strstr(uri, "/../") != NULL) return 1;
    size_t n = strlen(uri);
    if (n >= 3 && strcmp(uri + n - 3, "/..") == 0) return 1;
    return 0;
}


int mapToPath(const char *uri, char *path, size_t pathsize) {
    const char *root = "Webpage";


    if (snprintf(path, pathsize, "%s%s", root, uri) >= (int)pathsize) return -1;
    struct stat st;


    if (stat(path, &st) == 0 && S_ISDIR(st.st_mode)) {
        size_t len = strlen(path);
        if (len + 1 >= pathsize) return -1;
        if (path[len - 1] != '/') { path[len] = '/'; path[len + 1] = '\0'; len++; }
        if (snprintf(path + len, pathsize - len, "index.html") >= (int)(pathsize - len)) return -1;


    } else if (uri[strlen(uri) - 1] == '/') {

        size_t len = strlen(path);
        if (snprintf(path + len, pathsize - len, "index.html") >= (int)(pathsize - len)) return -1;

    }
    return 0;
}



const char *guess_mime(const char *path) {
    const char *dot = strrchr(path, '.');

    // getting the dot and then checking the correct extention type
    if (!dot) return "application/octet-stream";
    if (!strcmp(dot, ".html") || !strcmp(dot, ".htm")) return "text/html";
    if (!strcmp(dot, ".css"))  return "text/css";
    if (!strcmp(dot, ".js"))   return "application/javascript";
    if (!strcmp(dot, ".png"))  return "image/png";
    if (!strcmp(dot, ".jpg") || !strcmp(dot, ".jpeg")) return "image/jpeg";
    if (!strcmp(dot, ".gif"))  return "image/gif";
    if (!strcmp(dot, ".txt"))  return "text/plain";
    return "application/octet-stream";

}


int main(int argc, char *argv[])
{
    if (argc != 3) {
        fprintf(stderr, "usage: ./http_server [server port] [DB port]\n");
        exit(1);
    }

    // port numbers from argv
    uint16_t HTTPPORT = (uint16_t)atoi(argv[1]);
    uint16_t DBPORT   = (uint16_t)atoi(argv[2]); 


    // creating tcp lisiting socket for 
    int lsock = makeTheListenSocket(HTTPPORT);

    // this is the main loop
    for (;;) {
        // getting the addres
        struct sockaddr_in cliaddr; socklen_t clen = sizeof(cliaddr);
        // accepting the connection 
        int cfd = accept(lsock, (struct sockaddr*)&cliaddr, &clen);

        // checking if the connectino did not work
        if (cfd < 0) {
            if (errno == EINTR) continue;
            perror("accept");
            continue;
        }

        // 408 behivor 
        recvTimeout(cfd, RECV_TIMEOUT_SEC);


        // ip address of the client 
        char ipbuf[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &cliaddr.sin_addr, ipbuf, sizeof(ipbuf));

        // reading the request 
        char reqline[MAX_REQ_LINE];
        ssize_t r = recv_line(cfd, reqline, sizeof(reqline));


        // checking if the request is empty    
        if (r <= 0) {
            // 408 
            printOutRequest(ipbuf, "(no request line)", "408 Request Timeout");
            sendHTML(cfd, "408 Request Timeout", "408 Request Timeout");
            close(cfd);
            continue;
        }


        // Chop some text from req
        if (r >= 2 && reqline[r-2] == '\r' && reqline[r-1] == '\n') {
            reqline[r-2] = '\0';
        }



        char method[16], uri[4096], version[16];
        if (sscanf(reqline, "%15s %4095s %15s", method, uri, version) != 3) {
            printOutRequest(ipbuf, reqline, "400 Bad Request");
            sendHTML(cfd, "400 Bad Request", "400 Bad Request");
            close(cfd);
            continue;
        }

        // if not get the write 501 error 
        if (strcmp(method, "GET") != 0) {
            printOutRequest(ipbuf, reqline, "501 Not Implemented");
            sendHTML(cfd, "501 Not Implemented", "501 Not Implemented");
            close(cfd);
            continue;
        }

        // drain headers (until empty line)
        char line[2048];
        int got_blank = 0;
        do {
            ssize_t n = recv_line(cfd, line, sizeof(line));
            if (n <= 0) { // timeout/close while reading headers
                printOutRequest(ipbuf, reqline, "408 Request Timeout");
                sendHTML(cfd, "408 Request Timeout", "408 Request Timeout");
                close(cfd);
                goto next_conn;
            }
            // checking if the line is empty
            if (n == 2 && line[0] == '\r' && line[1] == '\n') {
                got_blank = 1;
            }
        } while (got_blank == 0);





        if (bad_uri(uri)) {
            printOutRequest(ipbuf, reqline, "400 Bad Request");
            sendHTML(cfd, "400 Bad Request", "400 Bad Request");
            close(cfd);
            goto next_conn;
        }
        //checking routes
        {
            char catkey[512];
            if (get_qparam(uri, "key", catkey, sizeof(catkey)) && catkey[0] != '\0') {
                // Decode the url
                if (url_decode_inplace(catkey) != 0) {
                    printOutRequest(ipbuf, reqline, "400 Bad Request");
                    sendHTML(cfd, "400 Bad Request", "400 Bad Request");
                    close(cfd);
                    goto next_conn;
                }

                // path separtors
                for (const char *p = catkey; *p; ++p) {
                    if (*p == '/' || *p == '\\') {
                        printOutRequest(ipbuf, reqline, "400 Bad Request");
                        sendHTML(cfd, "400 Bad Request", "400 Bad Request");
                        close(cfd);
                        goto next_conn;
                    }

                }

                unsigned char *data = NULL; size_t dlen = 0;
                int rc = udp_fetch_file(DBPORT, catkey, &data, &dlen);

                if (rc == -2) {  // not found
                    printOutRequest(ipbuf, reqline, "404 Not Found");
                    sendHTML(cfd, "404 Not Found", "404 Not Found");
                    close(cfd);
                    goto next_conn;
                }
                if (rc != 0) {   // timeout
                    printOutRequest(ipbuf, reqline, "408 Request Timeout");
                    sendHTML(cfd, "408 Request Timeout", "408 Request Timeout");
                    close(cfd);
                    goto next_conn;
                }




                // return jpg
                const char *mime = "image/jpeg";
                char hdr[256];
                int hlen = snprintf(hdr, sizeof(hdr),
                    "HTTP/1.0 200 OK\r\n"
                    "Content-Length: %zu\r\n"
                    "Content-Type: %s\r\n"
                    "\r\n", dlen, mime);
                if (sendAll(cfd, hdr, (size_t)hlen) == 0) {
                    (void)sendAll(cfd, data, dlen);
                }
                free(data);

                printOutRequest(ipbuf, reqline, "200 OK");
                close(cfd);
                goto next_conn;
            }
        }



        
        {
            char path[4096];
            if (mapToPath(uri, path, sizeof(path)) < 0) {
                printOutRequest(ipbuf, reqline, "400 Bad Request");
                sendHTML(cfd, "400 Bad Request", "400 Bad Request");
                close(cfd);
                goto next_conn;
            }

            int fd = open(path, O_RDONLY);
            if (fd < 0) {
                printOutRequest(ipbuf, reqline, "404 Not Found");
                sendHTML(cfd, "404 Not Found", "404 Not Found");
                close(cfd);
                goto next_conn;
            }

            struct stat st;
            if (fstat(fd, &st) < 0 || !S_ISREG(st.st_mode)) {
                close(fd);
                printOutRequest(ipbuf, reqline, "404 Not Found");
                sendHTML(cfd, "404 Not Found", "404 Not Found");
                close(cfd);
                goto next_conn;
            }

            const char *mime = guess_mime(path);
            char hdr[512];
            int hlen = snprintf(hdr, sizeof(hdr),
                "HTTP/1.0 200 OK\r\n"
                "Content-Length: %ld\r\n"
                "Content-Type: %s\r\n"
                "\r\n", (long)st.st_size, mime);
            if (sendAll(cfd, hdr, (size_t)hlen) < 0) {
                close(fd); close(cfd); goto next_conn;
            }

            // stream file
            char buf[4096];
            ssize_t n;
            while ((n = read(fd, buf, sizeof(buf))) > 0) {
                if (sendAll(cfd, buf, (size_t)n) < 0) { break; }
            }
            close(fd);

            printOutRequest(ipbuf, reqline, "200 OK");
            close(cfd);
        }

    next_conn:
        ;
    }
}
