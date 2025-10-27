/* The code is subject to Purdue University copyright policies.
 * Do not share, distribute, or post online.
 */

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <netdb.h>
#include <arpa/inet.h>

#define MYADDR "127.0.0.1"

#define FILENAMESIZE 1000

#define MAXUDPPKTSIZE 65536
#define SENDBUFSIZE 4096


int main(int argc, char *argv[])
{
    if (argc != 2) {
        fprintf(stderr, "usage: ./db_server [DB port]\n");
        exit(1);
    }

    unsigned short MYPORT = atoi(argv[1]);

	int sockfd;
	struct sockaddr_in my_addr;
	struct sockaddr_in their_addr;

	if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) == -1) {
		perror("socket");
		exit(1);
	}

    struct hostent *he;
    if ((he = gethostbyname(MYADDR)) == NULL) {
		perror("gethostbyname");
		exit(1);
	}
    my_addr.sin_family = AF_INET;
    my_addr.sin_addr = *((struct in_addr *)he->h_addr_list[0]);
    my_addr.sin_port = htons(MYPORT);

	if (bind(sockfd, (struct sockaddr *)&my_addr, sizeof(struct sockaddr)) == -1) {
		perror("bind");
		exit(1);
	}

	while(1) {
        int numbytes;
		socklen_t size = sizeof(struct sockaddr);
        char filename[MAXUDPPKTSIZE];



		if ((numbytes = recvfrom(sockfd, filename, MAXUDPPKTSIZE, MSG_WAITALL,
        (struct sockaddr *) &their_addr, &size)) == -1) {
			perror("recvfrom");
			exit(1);
		}
        filename[numbytes] = '\0';

        fprintf(stderr, "Received request for '%s'\n", filename);

        char filepath[FILENAMESIZE];
        strcpy(filepath, "cat_database/");
        strcat(filepath, filename);
        strcat(filepath, ".jpg");
        strcat(filepath, "\0");

        
        if (access(filepath, R_OK) != 0) { //file not found!
            if (sendto(sockfd, "File Not Found", 14, 0,
            (struct sockaddr *) &their_addr, size) == -1) {
                perror("sendto");
                exit(1);
            }
            fprintf(stderr, "File '%s' not found\n", filepath);
            continue;

        } else {
            int bytes = 0;

            int fd = open(filepath, O_RDONLY);

            do {
                char dst_buff[SENDBUFSIZE];
                bytes = read(fd, dst_buff, SENDBUFSIZE);

                if (bytes != 0) {
                    if (sendto(sockfd, dst_buff, bytes, 0,
                    (struct sockaddr *) &their_addr, size) == -1) {
                        perror("sendto");
                        exit(1);
                    }
                    fprintf(stderr, "File '%s': %d bytes sent\n", filepath, bytes);

                } else {
                    if (sendto(sockfd, "DONE", 4, 0,
                    (struct sockaddr *) &their_addr, size) == -1) {
                        perror("sendto");
                        exit(1);
                    }
                    fprintf(stderr, "File '%s' successfully sent\n", filepath);
                }

                usleep(1000);

            } while (bytes != 0);
        }
    }

	close(sockfd);

    return 0;
}

