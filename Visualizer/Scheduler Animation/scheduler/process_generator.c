
#include "headers.h"

void clearResources(int);

int msgq_id = 0;

typedef struct process_node {
    Process data;
    struct process_node* next;
} Process_Node;

Process_Node* new_process(int id, int AT,int RT,int pri, int memsize);
void ReadFile(char filename[],Process_Node** start);

int main(int argc, char *argv[])
{
    signal(SIGINT, clearResources);

    char* input_file = argv[1];
    int opt = ' ';
    int sch = -1, quantum = -1;
    Process_Node* start = new_process(0,0,0,0,0);

    for (int i = 2; i < argc; i++) {
        if (strcmp(argv[i], "-sch") == 0) {
            if (i + 1 < argc) {
                sch = atoi(argv[i + 1]);
                i++;
            } else {
                printf("Error: -sch flag requires a value.\n");
                return 1;
            }
        } 
        else if (strcmp(argv[i], "-q") == 0) {
            if (i + 1 < argc) {
                quantum = atoi(argv[i + 1]);
                i++;
            }
        }
    }

    ReadFile(input_file,&start);

    // TODO Initialization
    // 1. Read the input files. ✅
    // 2. Read the chosen scheduling algorithm and its parameters, if there are any from the argument list. ✅
    // 3. Initiate and create the scheduler and clock processes. ✅
    // 4. Use this function after creating the clock process to initialize clock. ✅

    key_t key_id;
    int send_val;
    key_id = ftok("keyfile", 65);
    msgq_id = msgget(key_id, 0666 | IPC_CREAT); 
    if (msgq_id == -1)
    {
        perror("Error in create");
        exit(-1);
    }
    printf("Message Queue ID = %d\n", msgq_id);

    int clk_fork = fork();
    if(clk_fork==0)
    {
        char *args_clk[]={"./clk.out",NULL};
        execv(args_clk[0],args_clk);
    }
    int sch_fork = fork();
    if(sch_fork==0)
    {
        char str_sch[2] = "";
        char str_qun[10] = "";
        sprintf(str_sch, "%d", sch);
        sprintf(str_qun, "%d", quantum);
        char *args_sch[]={"./scheduler.out","-sch",str_sch,"-q",str_qun,NULL};
        if (quantum == -1)
        {
            args_sch[3] = NULL;
            args_sch[4] = NULL;
        }
        execv(args_sch[0],args_sch);
    }
    initClk();
    // To get time use this function. 
    int x = getClk();
    printf("Current Time is %d\n", x);

    // TODO Generation Main Loop
    // 5. Create a data structure for processes and provide it with its parameters. ✅
    // 6. Send the information to the scheduler at the appropriate time. ✅
    // 7. Clear clock resources

    Process_Node* current = start;
    
    while(current != NULL)
    {
        x = getClk();
        while(current != NULL && x >= current->data.AT)
        {
            //send data via message queue to scheduler
            printf("send message %d,%d\n",current->data.Id,x);
            Msg_Buffer msg = {1,1,current->data};
            send_val = msgsnd(msgq_id, &msg, sizeof(msg)-sizeof(long), !IPC_NOWAIT);
            if (send_val == -1)
                perror("Errror in send");
            else
                current = current->next;
        }
    }
    Msg_Buffer msg = {1,-1,start->data};
    send_val = msgsnd(msgq_id, &msg, sizeof(msg)-sizeof(long), !IPC_NOWAIT);
    if (send_val == -1)
        perror("Errror in send");
    int stat = 0;
    waitpid(sch_fork,&stat,0);
    destroyClk(true);
}

void clearResources(int signum)
{
    //TODO Clears all resources in case of interruption
    msgctl(msgq_id, IPC_RMID, (struct msqid_ds *)0);
}

Process_Node* new_process(int id, int AT,int RT,int pri, int memsize)
{
    Process_Node* p = (Process_Node*) malloc(sizeof(Process_Node));
    p->data.Id = id;
    p->data.AT = AT;
    p->data.RT = RT;
    p->data.rem_time = RT;
    p->data.pri= pri;
    p->data.memsize=memsize;
    p->next = NULL;
    //printf("Id: %d,AT: %d,RT: %d,Pri: %d,memsize: %d\n",id,AT,RT,pri,memsize);
    return p;
}

void ReadFile(char filename[],Process_Node** start)
{
	FILE* file = fopen(filename, "r");
    if (file == NULL)
    {
        return;
    }
    char temp = ' ';
	int id=0 ,AT=0 ,RT=0 , pri=0, memsize=0;
    Process_Node* current = *start;


    while (fscanf(file,"%c",&temp) == 1)
    {
        if (temp == '#')
        {
            while (fscanf(file,"%c",&temp) && temp != '\n');
        }
        else
        {
            id = temp - '0';
            while (fscanf(file,"%c",&temp) && temp != '\t')
            {
                id = id*10 + temp - '0';
            }
            //fscanf(file, "%d\t%d\t%d\n", &AT,&RT,&pri);
            fscanf(file, "%d\t%d\t%d\t%d\n", &AT,&RT,&pri,&memsize);
            current->next  = new_process(id,AT,RT,pri,memsize);
            //current->next  = new_process(id,AT,RT,pri,1);
            current = current->next ;
        }
    }
    current = *start;
    *start = (*start)->next;
    free(current);
    fclose(file);
}
