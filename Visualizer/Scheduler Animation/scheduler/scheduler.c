#include "RR.h"
#include "SJF.h"
#include "headers.h"
#include "process_table.c"
#include "HPF.c"
#include "RR_queue.h"
#include "multi.h"
#include <errno.h>

typedef struct
{
    void *algo_obj; // pointer to actual scheduling algorithim object
    bool (*add)(void *, Process *);
    void (*run)(void *);
    void (*terminate)(int);
} AlgoInterface;

static AlgoInterface algo;

static void create_algo()
{
    algo.algo_obj = NULL;
    algo.add = NULL;
    algo.run = NULL;
    algo.terminate = NULL;
}

int main(int argc, char *argv[])
{
    initClk();
    // TODO: implement the scheduler.
    int sch = -1, quantum = -1;
    for (int i = 1; i < argc; i++)
    {
        if (strcmp(argv[i], "-sch") == 0)
        {
            if (i + 1 < argc)
            {
                sch = atoi(argv[i + 1]);
                i++;
            }
            else
            {
                printf("Error: -sch flag requires a value.\n");
                return 1;
            }
        }
        else if (strcmp(argv[i], "-q") == 0)
        {
            if (i + 1 < argc)
            {
                quantum = atoi(argv[i + 1]);
                i++;
            }
        }
    }

    //TODO: Select scheduling algorithm
    RR_Queue noMemoryQ;
    RR_Queue rrQ;
    create_default_rr_q(&noMemoryQ);
    
    create_algo();
    if (sch == 0) {
        create_default_pq();
        create_default_sjf();
        algo.add = sjf_default.add;
        algo.run = sjf_default.Run;
        algo.terminate = sjf_default.terminate;
        algo.algo_obj = &sjf_default;
    } else if(sch == 1) {
        create_default_pq();
        create_default_hpf();
        algo.add = hpf_default.add;
        algo.run = hpf_default.Run;
        algo.terminate = hpf_default.terminate;
        algo.algo_obj = &hpf_default;      
    }else if(sch == 2) {
        create_default_rr(quantum);
        algo.add = rr_default.add;
        algo.run = rr_default.Run;
        algo.terminate = rr_default.terminate;
        algo.algo_obj = &rr_default;
    }
     else if(sch == 3) {
        create_default_pq();
        create_default_multi(quantum);
        algo.add = multi_default.add;
        algo.run = multi_default.Run;
        algo.algo_obj = &multi_default;
        algo.terminate = multi_default.terminate;
    }

    signal(SIGUSR1,algo.terminate);

    // Recieve data from process_generator
    key_t key_id;
    int rec_val, msgq_id;

    key_id = ftok("keyfile", 65);               // create unique key
    msgq_id = msgget(key_id, 0666 | IPC_CREAT); // create message queue and return id

    if (msgq_id == -1)
    {
        perror("Error in create");
        exit(-1);
    }
    printf("Message Queue ID = %d\n", msgq_id);

    Msg_Buffer message;
    create_process_table();

    int prev_clk = -1;
    RR_Node* tempnode = (RR_Node*) malloc(sizeof(RR_Node));
    while (true)
    {
        if (prev_clk == getClk())
            continue;
        prev_clk = getClk();
        sleep(0.08);
        tempnode= noMemoryQ.peek(&noMemoryQ);
        if(tempnode!=NULL){
          while(tempnode!=NULL&&algo.add(algo.algo_obj,tempnode->data)){
            tempnode = noMemoryQ.dequeue(&noMemoryQ);
            PCB *new_pcb = (PCB *)malloc(sizeof(PCB));
            new_pcb->ex_t = tempnode->data->RT;
            new_pcb->id = tempnode->data->Id;
            new_pcb->rem_t = tempnode->data->RT;
            new_pcb->state = 0;
            new_pcb->wait_t = getClk() - tempnode->data->AT;
            process_table.insert(new_pcb);
            tempnode = noMemoryQ.peek(&noMemoryQ);
          }
        }
        rec_val = msgrcv(msgq_id, &message, sizeof(message) - sizeof(long), 0, IPC_NOWAIT);
        if (rec_val == -1)
        {
            if (errno != ENOMSG)
                perror("Error in receive");
        }
        while (message.request_id != -1 && rec_val != -1)
        {

            printf("\nMessage received: %d,%d\n", message.data.Id,getClk());
            //TODO: Insert message.data into PCB
            Process* new = (Process*) malloc(sizeof(Process));
            new->AT = message.data.AT;
            new->Id = message.data.Id;
            new->RT = message.data.RT;
            new->rem_time = message.data.RT;
            new->pri = message.data.pri;
            new->memsize = message.data.memsize;
            if(algo.add(algo.algo_obj,new)){
              PCB *new_pcb = (PCB *)malloc(sizeof(PCB));
              new_pcb->ex_t = new->RT;
              new_pcb->id = new->Id;
              new_pcb->rem_t = new->RT;
              new_pcb->state = 0;
              new_pcb->wait_t = 0;
              process_table.insert(new_pcb);
            }else{
              RR_Node* node = (RR_Node*) malloc(sizeof(RR_Node));
              node->data = new;
              noMemoryQ.insert(&noMemoryQ,node);
            }

            

            rec_val = msgrcv(msgq_id, &message, sizeof(message) - sizeof(long), 0, IPC_NOWAIT);
            if (rec_val == -1)
            {
                if (errno != ENOMSG)
                    perror("Error in receive");
            }
        }
 
        algo.run(algo.algo_obj);

        if (message.request_id == -1 && process_table.head == NULL && getClk() > 1)
          break;
    }

    sFile = fopen("Scheduler_perf.txt", "w");
    fprintf(sFile,"CPU utilization = %f\nAvg WTA = %f\nAvg Waiting = %f",((double)(getClk()-IdleTime)/(double)getClk()) * 100,TWTT/(double)N,(double)TWT/(double)N);
    fclose(sFile);
    fclose(pFile);
    fclose(mFile);
        /*
    Process *temp = NULL;
    printf("This is the content of the SJF queue\n");
    while(!algo.queue.is_empty(&algo.queue))
    {
        temp = algo.deq(&algo);
        printf("%d\n",temp->RT);
    }
    */
    // TODO: upon termination release the clock resources.

    destroyClk(true);
    exit(0);
    return 0;
}
