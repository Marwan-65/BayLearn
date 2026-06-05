
#pragma once
#include "process_table.c"
#include "RR_queue.h"
#include "RR.h"

FILE *pFile = NULL;
FILE *rFile = NULL;


void rr_add(void* ptr,Process* toinsert)
{
    RR* this = (RR*) ptr;
    RR_Node* node = (RR_Node*) malloc(sizeof(RR_Node));
    node->data = toinsert;
    this->queue.insert(&(this->queue.start),node);
    printf("\nprocess %d arrival time is %d\n", toinsert->Id, getClk()); 
}
Process* rr_deq(void* ptr)
{
    RR* this = (RR*) ptr;
    RR_Node* node = this->queue.dequeue(&(this->queue.start));
    return node->data;
}

void rr_run(void* ptr)
{
    RR* this = (RR*) ptr;
    if(this->queue.is_empty(&(this->queue)) && this->running == NULL)
        return;

    if (this->running != NULL)
    {
        printf("\nfrom scheduler process %d remaing time is %d\n", this->running->Id, this->running->rem_time); 
        fflush(stdout);  
        this->running->rem_time -= 1;
        process_table.inc_times(this->running->Id);
        if(this->running->rem_time == 0)
        {
            PCB* finished_pcb = process_table.remove(this->running->Id);
            Process* finished = this->running;

            if(finished_pcb != NULL)
            {
                int TA = getClk() - this->running->AT;
                float WTA = TA / this->running->RT;
                fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\n",getClk(),this->running->Id,this->running->AT,this->running->RT,0,finished_pcb->wait_t,TA,WTA);
                fflush(pFile);
                free(finished_pcb);
            }

        } else if (!this->queue.is_empty(&(this->queue)) && ((this->running->RT-this->running->rem_time)%this->quantum==0)) { //if the top of the queue has lower piority value 

            PCB* suspended_pcb = process_table.update_pcb(this->running->Id,0,this->running->rem_time);
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,0,suspended_pcb->wait_t);
            rr_add(this,this->running);
            //kill(suspended_pcb->pid,SIGUSR1);

        }
    }

    if ((this->running != NULL && ((!this->queue.is_empty(&(this->queue)) && ((this->running->RT-this->running->rem_time)%this->quantum==0)) || this->running->rem_time == 0 )) || this->running == NULL) //if no running or running but its remaining time is zero or there is lower piority value than it. So we need to change the running and update the PCB 
    {
        this->running = this->deq(this);

        if(this->running != NULL)
        {
            PCB* running_pcb = process_table.update_pcb(this->running->Id,1,this->running->rem_time);
            if(this->running->RT == this->running->rem_time)
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,0,running_pcb->wait_t);
            else
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,0,running_pcb->wait_t);
            fflush(pFile);
            //kill(running_pcb->pid,SIGUSR2);
        }
        else
            fclose(pFile);
    }
}

static RR rr_default;
static void create_default_rr(int q)
{
    rr_default.running = NULL;
    rr_default.queue = default_rr_queue;
    rr_default.add = &rr_add;
    rr_default.Run = &rr_run;
    rr_default.deq = &rr_deq;
    rr_default.quantum=q;
    pFile = fopen("Scheduler_log.txt", "w");
}

//To do : handling remaining time update responsibility
//To do : fix wait time
//To do : uncomment signals after fixing forking in scheduler

