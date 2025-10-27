/* The code is subject to Purdue University copyright policies.
 * Do not share, distribute, or post online.
 */

 #include <stdio.h>
 #include <stdlib.h>
 #include <errno.h>
 #include <string.h>
 #include <unistd.h>
 #include <sys/types.h>
 #include <netinet/in.h>
 #include <sys/socket.h>
 #include <sys/wait.h>
 #include <netdb.h>
 #include <arpa/inet.h>
 #include <fcntl.h>
 #include <sys/stat.h>  
 
 
 int main(int argc, char *argv[])
 {
     if (argc != 4) {
         fprintf(stderr, "usage: ./http_client [host] [port number] [filepath]\n");
         exit(1);
     }
 
     char *host = argv[1];
     int portNumber = atoi(argv[2]);
     char *filePath = argv[3];
     int buffer_size = 4096;
     
 
     char * fileName;
     if(strcmp(filePath, "/") == 0){ 
         fileName = "index.html";
     }else{
         fileName = strrchr(filePath, '/');
         if(fileName != NULL){
             fileName ++;
         }else{
             fileName = filePath;
         }
     }
 
 
 
 
     struct hostent *hostNameDNS = gethostbyname(host);
     if(hostNameDNS == NULL){
         herror("gethostbyname");
         exit(1);
     }
 
 
     int clientSocket = socket(AF_INET, SOCK_STREAM, 0);
     if(clientSocket < 0){
         perror("socket");
         exit(1);
     }
 
     struct sockaddr_in serv = {
         .sin_family = AF_INET,
         .sin_port = htons(portNumber),
         .sin_addr = *((struct in_addr *)hostNameDNS->h_addr_list[0])
     };
 
 
 
     if(connect(clientSocket, (struct sockaddr *)&serv, sizeof(serv)) < 0){
         close(clientSocket);
         exit(1);
     }
     printf("connected\n");
 
 
     char request[1024];
     int res = snprintf(request, sizeof(request),
              "GET %s HTTP/1.0\r\n"
              "Host: %s:%d\r\n"
              "\r\n",
              filePath, host, portNumber);
 
 
     if(res < 0 || res >= sizeof(request)){
         close(clientSocket);
         exit(1);
     }
 
     if(send(clientSocket, request, strlen(request), 0) < 0){
         close(clientSocket);
         exit(1);
     }
 
 
     
 
 
     char response[1000000];
     char buffer[buffer_size];
     int total = 0;
     int numberOfBytes;
     
 
     while((numberOfBytes = recv(clientSocket, buffer, buffer_size, 0)) > 0){
         if(total + numberOfBytes >= 1000000){
             printf("to big");
             close(clientSocket);
             exit(1);
         }
 
         memcpy(response + total, buffer, numberOfBytes);
         total += numberOfBytes;
         printf("Total so far: %d bytes\n", total);
         
     }
     response[total] = '\0';
 
     if(numberOfBytes < 0){
         close(clientSocket);
         exit(1);
     }
 
     char *start = strstr(response, "\r\n\r\n");
     if(start == NULL){
         close(clientSocket);
         exit(1);
     }
     start+=4;
 
     //checking the status of the http response
 
 
     char statusLine[256];
     int j = 0;
     while(response[j] != '\n' && response[j] != '\r' && j < 255){
         statusLine[j] = response[j];
         j++;
     }
 
     statusLine[j] = '\0';
     printf("Found header end, status line: %s\n", statusLine);
 
 
     if(strstr(statusLine, "200") == NULL){
         printf("%s\n", statusLine);
         close(clientSocket);
         exit(1);
     }
     printf("Status check passed\n");
 
 
 
     char *cl = strstr(response, "Content-Length:");
     if (cl == NULL) {
         cl = strstr(response, "content-length:");
     }
 
 
 
     
     if (cl == NULL) {
         printf("Could not download the requested file (content length unknown)\n");
         close(clientSocket);
         exit(1);
     }
     
     cl += 15; // Skip "Content-Length:"
     while (*cl == ' '){ 
         cl++;
     
     }
     int content_length = atoi(cl);
     
 
 
     FILE *file = fopen(fileName, "wb");
     if (file == NULL) {
         perror("fopen");
         exit(1);
     }   
     printf("File opened successfully: %s\n", fileName);
 
 
 
     int content_received = total - (start - response);
     int bytes_to_write = (content_received < content_length) ? content_received : content_length;
 
     if(bytes_to_write > 0) {
         fwrite(start, 1, bytes_to_write, file);
         printf("Wrote %d bytes to file\n", bytes_to_write);
 
     }
 
     
     //fwrite(start, 1, content_length, file);
     fclose(file);    
     close(clientSocket);
     return 0;
 }