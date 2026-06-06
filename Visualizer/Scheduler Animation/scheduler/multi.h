#pragma once
#include "priority_queue.h"
#include "process_table.c"

int lastSwitch_m;

typedef struct multilevel {
    Process* running;
    Pri_Queue queue;
    int running_pri;
    int quantum;
    bool (*add)(void*, Process*);
    Pri_Node* (*deq)(struct multilevel*);
    void (*Run)(void*);
    void (*terminate)(int);
} multi;

bool add_funn(void* ptr, Process* toinsert)  // Changed 'ml' to 'ml'
{
    multi* ml = (multi*) ptr;
    Pri_Node* node = (Pri_Node*) malloc(sizeof(Pri_Node));
    if(!found(root, toinsert->Id)){
        Memory *temp = occupyMemory(root, toinsert);
        if (temp == NULL)
            return false;
        fprintf(mFile, "At time %d allocated %d bytes for process %d from %d to %d\n", getClk() , toinsert->memoryBlock->size, toinsert->Id, toinsert->memoryBlock->startAddress, toinsert->memoryBlock->startAddress + toinsert->memoryBlock->size - 1);
        fflush(mFile);
    }
    node->data = toinsert;

    if(toinsert->pri <= 2)
    {
        node->pri = 0;
    }
    else if(toinsert->pri <= 5)
    {
        node->pri = 1;
    }
    else if(toinsert->pri <= 8)
    {
        node->pri = 2;
    }
    else
    {
        node-> pri=3;
    }
    
    ml->queue.insert(&(ml->queue.start), node);  // Changed 'ml' to 'ml'
    printf("insterted process %d with pri %d\n",toinsert->Id,node->pri);
    ml->queue.print(ml->queue.start);
    return true;
}

void restart(multi* ml)  // Changed 'ml' to 'ml'
{
    printf("entered restart\n");
    Pri_Queue temp= default_pri_queue;
    Pri_Node* node=(Pri_Node*) malloc(sizeof(Pri_Node));
    printf("before restarting\n");
    ml->queue.print(ml->queue.start);
    while(!ml->queue.is_empty(&(ml->queue)))
    {
        node=ml->deq(ml);
        node->pri=0;
        temp.insert(&(temp.start), node); 
    }
    
     while(!temp.is_empty(&temp))
    {
        node=temp.dequeue(&(temp.start));
        add_funn(ml,node->data);
    }
    printf("after restarting\n");
    ml->queue.print(ml->queue.start);
    printf("exited restart\n");
    return;
}

int reinsert(multi* ml, Process* toinsert, int old_pri)  // Changed 'ml' to 'ml'
{
    int restart = 0;
    Pri_Node* node = (Pri_Node*) malloc(sizeof(Pri_Node));
    node->data = toinsert;
    if (old_pri<=3)
    {
        node->pri = old_pri +1;
    }
    else
    {
        node->pri = old_pri;
    }
    ml->queue.insert(&(ml->queue.start), node);
    if(ml->queue.start->pri==4) // if the process at the start is in the last level then restart
    {
        restart = 1;
    }
    printf("reinsterted process %d with pri %d\n",toinsert->Id,node->pri);
    ml->queue.print(ml->queue.start);
    return restart;
}

Pri_Node* deq_funn(multi* ml)  // Changed 'ml' to 'ml'
{
    Pri_Node* node = ml->queue.dequeue(&(ml->queue.start));  // Changed 'ml' to 'ml'
    return node;
}

void run_funn(void* ptr)
{
    multi* ml = (multi*) ptr;
    int rest=0;
    if(ml->queue.is_empty(&(ml->queue)) && ml->running == NULL)
    {
      if(getClk()>0)
        IdleTime++;
      return;
    }

    if (ml->running != NULL && ml->running->rem_time != 0)
    {
        if ((getClk()-lastSwitch_m)%ml->quantum==0) {
            int old_level = ml->running_pri;
            ml->running->rem_time -= (getClk() - lastSwitch_m);
            PCB* suspended_pcb = process_table.update_pcb(ml->running->Id,0,ml->running->rem_time);
            rest=reinsert(ml,ml->running,old_level);
            if(rest)
            {
                restart(ml);
            }
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d with pri: %d\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,suspended_pcb->wait_t,ml->running->pri);
            if(rest)
            {
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: QUANTUM_EXPIRE+STARVATION_RESET — quantum of %d expired at the lowest level (3); re-insertion of a level-3 process triggered the anti-starvation reset: all processes moved back to level 0 to prevent indefinite starvation\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,suspended_pcb->wait_t,ml->quantum);
            }
            else
            {
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: QUANTUM_EXPIRE+DEMOTED — consumed full quantum of %d time unit(s); demoted from level-%d to level-%d (each quantum expiry moves the process one level lower in priority)\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,suspended_pcb->wait_t,ml->quantum,old_level,old_level+1);
            }
            fflush(pFile);
            fflush(rFile);
            kill(suspended_pcb->pid,SIGSTOP);
        }
    }

    if ((ml->running != NULL && ((!ml->queue.is_empty(&(ml->queue)) && ((getClk()-lastSwitch_m)%ml->quantum==0)) || ml->running->rem_time == 0 )) || (ml->running == NULL)) 
    {
        bool idle = (ml->running == NULL);
        Pri_Node* mohsin=ml->deq(ml);
        
        if(mohsin != NULL)
        {
            ml->running = mohsin->data;
            ml->running_pri=mohsin->pri;
            PCB* running_pcb = process_table.update_pcb(ml->running->Id,1,ml->running->rem_time);
            running_pcb->wait_t = getClk() - ml->running->AT - (ml->running->RT - ml->running->rem_time);
            if(ml->running->RT == ml->running->rem_time)
            {
                int process_fork = fork();
                if(process_fork == 0)
                {
                    char run_time[8] = "";
                    sprintf(run_time, "%d", running_pcb->rem_t);
                    char *args_sch[]={run_time,NULL};
                    execv("./process.out", args_sch);
                }
                running_pcb->pid = process_fork;
                fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d with pri: %d\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,running_pcb->wait_t,ml->running->pri);
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: FIRST_RUN — entered CPU from level-%d queue (pri 1-2 → L0, pri 3-5 → L1, pri 6-8 → L2, pri 9+ → L3); waited %d time unit(s) since arrival at t=%d\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,running_pcb->wait_t,ml->running_pri,running_pcb->wait_t,ml->running->AT);
            }
            else
            {
                fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d with pri: %d\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,running_pcb->wait_t,ml->running->pri);
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: RESUMED — re-scheduled from level-%d queue (level 0=highest, level 3=lowest); %d time unit(s) remaining out of original burst of %d\n",getClk(),ml->running->Id,ml->running->AT,ml->running->RT,ml->running->rem_time,running_pcb->wait_t,ml->running_pri,ml->running->rem_time,ml->running->RT);
                kill(running_pcb->pid,SIGCONT);
            }
            fflush(pFile);
            fflush(rFile);
            lastSwitch_m = getClk();
        }
        else
        {
            if(idle)
                IdleTime++;
        }
    }
}

static multi multi_default;

void multi_terminated(int signum) {
    //fflush(stdout);
    multi_default.running->rem_time = 0;
    PCB* finished_pcb = process_table.remove(multi_default.running->Id);
    Process* finished = multi_default.running;

    if(finished_pcb != NULL)
    {
        int TA = getClk() - multi_default.running->AT;
        float WTA = (float)TA / multi_default.running->RT;
        TWT += finished_pcb->wait_t;
        TWTT += WTA;
        N++;
        fprintf(mFile, "At time %d freed %d bytes from process %d from %d to %d\n", getClk(), finished->memoryBlock->size, finished->Id, finished->memoryBlock->startAddress, finished->memoryBlock->startAddress + finished->memoryBlock->size - 1);
        fflush(mFile);
        freeMemory(root, finished->Id);
        fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\n",getClk(),multi_default.running->Id,multi_default.running->AT,multi_default.running->RT,0,finished_pcb->wait_t,TA,WTA);
        fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\treason: COMPLETED — total burst of %d time unit(s) fully consumed; process finished its final time slice within a quantum\n",getClk(),multi_default.running->Id,multi_default.running->AT,multi_default.running->RT,0,finished_pcb->wait_t,TA,WTA,multi_default.running->RT);
        fflush(pFile);
        fflush(rFile);
        free(finished_pcb);
    }
    multi_default.running = NULL;
}

static void create_default_multi(int q)
{
    multi_default.running = NULL;
    multi_default.queue = default_pri_queue;
    multi_default.add = &add_funn;
    multi_default.Run = &run_funn;
    multi_default.deq = &deq_funn;
    multi_default.quantum=q;
    multi_default.terminate = &multi_terminated;
    pFile = fopen("Scheduler_log.txt", "w");
    mFile = fopen("Memory_log.txt", "w");
    rFile = fopen("reason_log.txt", "w");
    root = createMemoryBlock(0, 1024);

}
