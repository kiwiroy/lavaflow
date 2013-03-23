# Copyright 2011 David Irvine
# 
# This file is part of LavaFlow
#
# LavaFlow is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published by 
# the Free Software Foundation, either version 3 of the License, or (at 
# your option) any later version.
#
# LavaFlow is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU 
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License 
# along with LavaFlow.  If not, see <http://www.gnu.org/licenses/>.
#
# $Rev: 158 $:   
# $Author: irvined $: 
# $Date: 2012-10-31 23:42:17 +0100 (Wed, 31 Oct 2012) $:  
#
import array
import datetime
import json
import logging
from django.db import models
from django.db.models import Avg, Count, Sum, Min, Max
from django.core.urlresolvers import reverse
from django.core.cache import cache
log=logging.getLogger(__name__)


class QuerySetManager(models.Manager):
	use_for_related_fields = True
	def __init__(self, qs_class=models.query.QuerySet):
		self.queryset_class = qs_class
		super(QuerySetManager, self).__init__()

	def get_query_set(self):
		return self.queryset_class(self.model)

	def __getattr__(self, attr, *args):
		try:
			return getattr(self.__class__, attr, *args)
		except AttributeError:
			return getattr(self.get_query_set(), attr, *args) 


class RunQuerySet(models.query.QuerySet):
	def utilizationN3DS(self, reportStartTime, reportEndTime,maxBlocks,filterString):
		return json.dumps(self.utilization(reportStartTime, reportEndTime,maxBlocks,filterString))
	def utilization(self, reportStartTime, reportEndTime,maxBlocks,filterString):
		log.debug("TEST")
		blockSize=60 # 60 second block size which will then be downsampled as required.
		reportStartTime=int(int(reportStartTime)/blockSize)*blockSize
		reportEndTime=int(int(reportEndTime)/blockSize)*blockSize
		
		actualBlocks=((reportEndTime-reportStartTime)/blockSize)+1

		running=array.array('l', [0]) * (actualBlocks)
		pending=array.array('l', [0]) * (actualBlocks)

		for run in self.filter(end_time__gte=reportStartTime, start_time__lte=reportEndTime).values('num_processors','element__job__submit_time','start_time','end_time'):
			cores=run['num_processors']
			startMinute=int(run['start_time']/blockSize)*blockSize
			endMinute=int(run['end_time']/blockSize)*blockSize
			subMinute=int(run['element__job__submit_time']/blockSize)*blockSize

			if (subMinute<=reportStartTime):
				pending[0]+=cores
			elif (subMinute<=reportEndTime):
				subBlock=int((subMinute-reportStartTime)/blockSize)
				pending[subBlock]+=cores

			if (startMinute<=reportStartTime):
				pending[0]-=cores
				running[0]+=cores
			elif (startMinute<=reportEndTime):
				startBlock=int((startMinute-reportStartTime)/blockSize)
				running[startBlock]+=cores
				pending[startBlock]-=cores

			if (endMinute<=reportEndTime):
				endBlock=int((endMinute-reportStartTime)/blockSize)
				running[endBlock]-=cores
		runningJobs=0
		pendingJobs=0

		for i in range(len(pending)):
			runningJobs+=running[i]
			running[i]=runningJobs
			pendingJobs+=pending[i]
			pending[i]=pendingJobs

		block=reportStartTime
		index=0

		# must downsize, find a slice size that works.:
		sliceSize=int(actualBlocks/maxBlocks)
		if sliceSize<1:
			sliceSize=1

		currentSliceStart=0
		rRunning=[]
		rPending=[]
		while (currentSliceStart<actualBlocks):
			currentSliceEnd=currentSliceStart+sliceSize
			if currentSliceEnd>=actualBlocks:
				currentSliceEnd=actualBlocks-1
				if currentSliceStart==currentSliceEnd:
					break
			sTime=(currentSliceStart*blockSize)+reportStartTime
			p=pending[currentSliceStart:currentSliceEnd]
			r=running[currentSliceStart:currentSliceEnd]

			pval=sum(p)/len(p)
			rval=sum(r)/len(r)
			rPending.append({
					'x':sTime,
					'y':pval,
				})
			rRunning.append({
					'x':sTime,
					'y':rval,
				})
			currentSliceStart+=sliceSize
		data=[
				{
					'key':'Slots In Use',
					'values':rRunning,
				},
				{
					'key':'Slots Requested',
					'values':rPending,
				},
			]
		return data
	
	def complexUtilization(self, reportStartTime, reportEndTime, maxBlocks, groups=[]):
		if len(groups)<1:
			raise ValueError

		seriesList=[]
		for run in self.filter(end_time__gte=reportStartTime, start_time__lte=reportEndTime).values(*groups).distinct(*groups):
			gdict={}
			groupName=""
			for group in groups:
				if len(groupName)>0:
					groupName+=" "
				groupName+=run[group]
				gdict[group]=run[group]
			runs=self.filter(**gdict)
			data=runs.utilization(reportStartTime, reportEndTime, maxBlocks,"")
			data[0]['key']=groupName+" Running"
			data[1]['key']=groupName+" Pending"
			seriesList.append(data[0])
			seriesList.append(data[1])
		return json.dumps(seriesList)


class Host(models.Model):
	host_name=models.CharField(max_length=100)
	def get_absolute_url(self):
		return reverse('lavaFlow.views.hostView', args=[self.id,])
	def __unicode__(self):
		return u'%s' % self.host_name
	def __str__(self):
		return self.host_name
	def hostUsage(self):
		info=self.executions.values('run__element__job__cluster','run__queue','run__runFinishInfo__exit_reason').annotate(
				numRuns=Count('run__num_processors'),
				).order_by('-numRuns')
		for i in info:
			i['cluster']=Cluster.objects.get(pk=i['run__element__job__cluster'])
			i['queue']=Queue.objects.get(pk=i['run__queue'])
			i['exit']=ExitReason.objects.get(pk=i['run__runFinishInfo__exit_reason'])
		return info
	def submittedJobs(self):
		return Job.objects.filter(submit_host=self).count()
	def executedJobs(self):
		return Job.objects.filter(runs__executions__host=self).distinct().count()

	def submitUsage(self):
		info=Run.objects.filter(element__job__submit_host=self).values('element__job__cluster','queue').annotate(
				numJobs=Count('element__job'),
				numTasks=Count('element'),
				numRuns=Count('num_processors'),
				cpu_time=Sum('cpu_time'),
				wall_time=Sum('wall_time'),
				)
		for i in info:
			i['cluster']=Cluster.objects.get(pk=i['element__job__cluster'])
			i['queue']=Queue.objects.get(pk=i['queue'])
			i['cpu_time']=datetime.timedelta(seconds=i['cpu_time'])
			i['wall_time']=datetime.timedelta(seconds=i['wall_time'])
		return info

class Service(models.Model):
	name=models.CharField(max_length=512)

class Outage(models.Model):
	service=models.ForeignKey(Service, related_name='outages')
	start_time=models.IntegerField()
	end_time=models.IntegerField()
	duration=models.IntegerField()
	host=models.ForeignKey(Host, related_name='outages')
	def get_absolute_url(self):
		raise NotImplementedError
	def duration_delta(self):
		return datetime.timedelta(seconds=self.duration)
	def start_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.start_time)
	def end_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.end_time)
	def run_list(self):
		return Run.objects.filter(start_time__gte=self.start_time, end_time__lte=self.end_time).filter(executions__host=self.host)
	def num_impacted_runs(self):
		return self.runList().count()

class OutageLog(models.Model):
	time=models.IntegerField()
	message=models.TextField()
	outage=models.ForeignKey(Outage, related_name="logEntries")
	def time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.time)


# Create your models here.
class ExitReason(models.Model):
	name=models.CharField(max_length=100)
	description=models.CharField(max_length=1024)
	value=models.IntegerField()
	def __unicode__(self):
		return u'%s' % self.name
	def __str__(self):
		return self.name
		
	def get_filter_string(self):
		return 'filter/exit_status_code/%s' % self.id



class JobStatus(models.Model):
    job_status=models.CharField(max_length=100)

class Cluster(models.Model):
	name=models.CharField(
			max_length=100,
			unique=True,
			help_text='The name of the cluster',
			)
	def __unicode__(self):
		return u'%s' % self.name
	def __str__(self):
		return self.name
	def get_absolute_url(self):
		end_time=self.lastJobExit()
		firstTime=self.firstSubmitTime()
		start_time=end_time-(7*24*60*60)
		if start_time<firstTime:
			start_time=firstTime
		return reverse('lavaFlow.views.homeView', args=[start_time,end_time,self.get_filter_string()])
	def get_filter_string(self):
		return 'filter/cluster/%s' % self.id
	def firstSubmitTime(self):
		time=cache.get('cluster_firstSubmitTime_%s' %self.id )
		if time:
			log.debug("firstSubmitTime: Read time from cache")
			return time
		else:
			time=Job.objects.filter(cluster=self).aggregate(Min('submit_time'))['submit_time__min']
			log.debug("firstSubmitTime: Writing time to cache")
			cache.set('cluster_firstSubmitTime_%s' %self.id, time, 360)
			return time
	def lastJobExit(self):
		time=cache.get('cluster_lastJobExit_%s' %self.id )
		if time:
			log.debug("lastJobExit: Read time from cache")
			return time
		else:
			time=Run.objects.filter(element__job__cluster=self).aggregate(Max('end_time'))['end_time__max']
			log.debug("lastJobExit: Writing time to cache")
			cache.set('cluster_lastJobExit_%s' %self.id, time, 360)
			return time
			
	def lastJobExitDT(self):
		return datetime.datetime.utcfromtimestamp(self.lastJobExit())
	def firstSubmitTimeDT(self):
		return datetime.datetime.utcfromtimestamp(self.firstSubmitTime())

	def userStats(self,field):
		users=self.jobs.values('user').annotate(
				numJobs=Count('job_id'),
				numTasks=Count('elements'),
				numRuns=Count('runs'),
				sumPend=Sum('runs__pend_time'),
				sumWall=Sum('runs__wall_time'),
				sumCpu=Sum('runs__cpu_time'),
				avgPend=Avg('runs__pend_time'),
				avgWall=Avg('runs__wall_time'),
				avgCpu=Avg('runs__cpu_time'),
				maxPend=Max('runs__pend_time'),
				maxWall=Max('runs__wall_time'),
				maxCpu=Max('runs__cpu_time'),
				minPend=Min('runs__pend_time'),
				minWall=Min('runs__wall_time'),
				minCpu=Min('runs__cpu_time'),
				).order_by(field)[0:10]
		for u in users:
			for f in [
				'sumPend',
				'sumWall',
				'sumCpu',
				'avgPend',
				'avgWall',
				'avgCpu',
				'maxPend',
				'maxWall',
				'maxCpu',
				'minPend',
				'minWall',
				'minCpu']:
				u[f]=datetime.timedelta(seconds=u[f])
			u['user']=User.objects.get(pk=u['user'])
		return users
	def busyUsers(self):
		return self.userStats('-sumCpu')
	def patientUsers(self):
		return self.userStats('-avgPend')

	def hostStats(self,order):
		hosts=self.jobs.values('runs__executions__host').annotate(
				numRuns=Count('runs')
				).order_by(order)[0:10]
		for h in hosts:
			try:
				h['host']=Host.objects.get(pk=h['runs__executions__host'])
			except:
				h['host']='None'
		return hosts
	def busyHosts(self):
		return self.hostStats('-numRuns')

	def failedHosts(self):
		hosts=self.jobs.exclude(runs__runFinishInfo__job_status__job_status="Done").values('runs__executions__host').annotate(
				numRuns=Count('runs')
				).order_by('-numRuns')[0:10]
		for h in hosts:
			try:
				h['host']=Host.objects.get(pk=h['runs__executions__host'])
			except:
				h['host']='None'

		return hosts
		
	def goodHosts(self):
		hosts=self.jobs.filter(runs__runFinishInfo__job_status__job_status="Done").values('runs__executions__host').annotate(
				numRuns=Count('runs')
				).order_by('-numRuns')[0:10]
		for h in hosts:
			try:
				h['host']=Host.objects.get(pk=h['runs__executions__host'])
			except:
				h['host']='None'
		return hosts
		
	def busySubmitHosts(self):
		hosts=self.jobs.values('submit_host').annotate(
				numRuns=Count('job_id')
				).order_by('-numRuns')[0:10]
		for h in hosts:
			try:
				h['host']=Host.objects.get(pk=h['submit_host'])
			except:
				h['host']='None'
		return hosts
	def totalJobs(self):
		return self.jobs.count()

	def totalTasks(self):
		return Task.objects.filter(job__cluster=self).count()
	def totalRuns(self):
		return Run.objects.filter(element__job__cluster=self).count()
	def cpu_time(self):
		return Run.objects.filter(element__job__cluster=self).aggregate(Sum('cpu_time'))['cpu_time__sum']
	def cpu_timedelta(self):
		return datetime.timedelta(seconds=self.cpu_time())
	def wall_time(self):
		return Run.objects.filter(element__job__cluster=self).aggregate(Sum('wall_time'))['wall_time__sum']
	def wall_timedelta(self):
		return datetime.timedelta(seconds=self.wall_time())
	def pend_time(self):
		return Run.objects.filter(element__job__cluster=self).aggregate(Sum('pend_time'))['pend_time__sum']
	def pend_timedelta(self):
		return datetime.timedelta(seconds=self.pend_time())

class Project(models.Model):
	name=models.CharField(max_length=100)
	def get_absolute_url(self):
		return '/lavaFlow/projectView/%s/' % self.id
	def submitUsage(self):
		info=self.runs.values('element__job__cluster','element__job__user','queue','num_processors').annotate(
				numJobs=Count('element__job'),
				numTasks=Count('element'),
				numRuns=Count('num_processors'),
				cpu=Sum('cpu_time'),
				wall=Sum('wall_time'),
				pend=Sum('pend_time'),
				avgCpu=Avg('cpu_time'),
				avgWall=Avg('wall_time'),
				avgPend=Avg('pend_time'),
				).order_by('element__job__cluster','element__job__user','queue','num_processors')
		for i in info:
			i['cluster']=Cluster.objects.get(pk=i['element__job__cluster'])
			i['user']=User.objects.get(pk=i['element__job__user'])
			i['queue']=Queue.objects.get(pk=i['queue'])
			i['cpu_time']=datetime.timedelta(seconds=i['cpu'])
			i['wall_time']=datetime.timedelta(seconds=i['wall'])
			i['pend_time']=datetime.timedelta(seconds=i['pend'])
			i['avgWall']=datetime.timedelta(seconds=i['avgWall'])
			i['avgPend']=datetime.timedelta(seconds=i['avgPend'])
			i['avgCpu']=datetime.timedelta(seconds=i['avgCpu'])
		return info

class User(models.Model):
	user_name=models.CharField(max_length=128)
	def __unicode__(self):
		return u'%s' % self.user_name
	def get_absolute_url(self):
		return reverse('lavaFlow.views.userView', args=[self.id,])
	def submitUsage(self):
		info=Run.objects.filter(element__job__user=self).values('element__job__cluster','queue','num_processors').annotate(
				numJobs=Count('element__job'),
				numTasks=Count('element'),
				numRuns=Count('num_processors'),
				cpu=Sum('cpu_time'),
				wall=Sum('wall_time'),
				pend=Sum('pend_time'),
				avgCpu=Avg('cpu_time'),
				avgWall=Avg('wall_time'),
				avgPend=Avg('pend_time'),

				)
		for i in info:
			i['cluster']=Cluster.objects.get(pk=i['element__job__cluster'])
			i['queue']=Queue.objects.get(pk=i['queue'])
			i['cpu_time']=datetime.timedelta(seconds=i['cpu'])
			i['wall_time']=datetime.timedelta(seconds=i['wall'])
			i['pend_time']=datetime.timedelta(seconds=i['pend'])
			i['avgWall']=datetime.timedelta(seconds=i['avgWall'])
			i['avgPend']=datetime.timedelta(seconds=i['avgPend'])
			i['avgCpu']=datetime.timedelta(seconds=i['avgCpu'])
		return info

	def runs(self):
		runs=Run.objects.filter(element__job__user=self)
		return runs


class Queue(models.Model):
	name=models.CharField(max_length=128)
	def __unicode__(self):
		return u'%s' % self.name
	def __str__(self):
		return self.name




class JobQuerySet(models.query.QuerySet):
	def uniqClusters(self):
		return self.values('cluster__name').distinct().count()

	def uniqUsers(self):
		return self.values('user__user_name').distinct().count()

	def wall_time(self):
		return self.aggregate(Sum('runs__wall_time'))['runs__wall_time__sum']

	def wall_timedelta(self):
		return datetime.timedelta(seconds=self.wall_time())

	def pend_time(self):
		return self.aggregate(Sum('runs__pend_time'))['runs__pend_time__sum']

	def pend_timedelta(self):
		return datetime.timedelta(seconds=self.pend_time())

	def cpu_time(self):
		return self.aggregate(Sum('runs__cpu_time'))['runs__cpu_time__sum']

	def cpu_timedelta(self):
		return datetime.timedelta(seconds=self.cpu_time())

class Job(models.Model):
	objects=QuerySetManager(JobQuerySet)
	job_id=models.IntegerField()
	cluster=models.ForeignKey(Cluster, related_name='jobs')
	user=models.ForeignKey(User, related_name='jobs')
	submit_host=models.ForeignKey(Host, related_name='submitted_jobs')
	submit_time=models.IntegerField()
	def get_absolute_url(self):
		return reverse('lavaFlow.views.jobDetailView', args=[self.id,])

	def wall_time(self):
		return self.runs.aggregate(Sum('wall_time'))['wall_time__sum']
	def wall_timedelta(self):
		return datetime.timedelta(seconds=self.wall_time())

	def pend_time(self):
		return self.runs.aggregate(Sum('pend_time'))['pend_time__sum']
	def pend_timedelta(self):
		return datetime.timedelta(seconds=self.pend_time())

	def cpu_time(self):
		return self.runs.aggregate(Sum('cpu_time'))['cpu_time__sum']

	def cpu_timedelta(self):
		return datetime.timedelta(seconds=self.cpu_time())

	def submit_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.submit_time)

	def first_start_time(self):
		return self.runs.aggregate(Min('start_time'))['start_time__min']
	def first_start_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.first_start_time())

	def last_finish_time(self):
		return self.runs.aggregate(Max('end_time'))['end_time__max']
	def last_finish_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.last_finish_time())

	def first_run(self):
		return self.runs.order_by('start_time')[0]
	def utilizationN3DS(self):
		return Run.objects.filter(job=self).utilizationN3DS(self.submit_time, self.last_finish_time(),100, "")

class Task(models.Model):
	task_id=models.IntegerField()
	job=models.ForeignKey(Job, related_name='elements')


class Run(models.Model):
	objects = QuerySetManager(RunQuerySet)
	job=models.ForeignKey(Job,related_name='runs')
	element=models.ForeignKey(Task, related_name='runs')
	num_processors=models.IntegerField()
	projects=models.ManyToManyField(Project, related_name='runs')
	start_time=models.IntegerField()
	end_time=models.IntegerField()
	cpu_time=models.IntegerField()
	wall_time=models.IntegerField()
	pend_time=models.IntegerField()
	queue=models.ForeignKey(Queue, related_name='runs')
	def otherRuns(self):
		hosts=self.executions.values('host').distinct()
		runs=Run.objects.filter(start_time__gte=self.start_time, start_time__lte=self.end_time).filter(end_time__gte=self.end_time).filter(executions__host__in=self.executions.values('host').distinct()).exclude(pk=self.id).distinct()
		return runs
	def pend_timedelta(self):
		return datetime.timedelta(seconds=self.pend_time)
	def wall_timedelta(self):
		return datetime.timedelta(seconds=self.wall_time)
	def cpu_timedelta(self):
		return datetime.timedelta(seconds=self.cpu_time)
	def start_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.start_time)

	def end_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.end_time)

	def get_absolute_url(self):
		return reverse("lavaFlow.views.runDetailView", args=[self.id,])

	def utilizationN3DS(self):
		runs=Run.objects.filter(pk=self.id)
		return runs.utilizationN3DS(self.element.job.submit_time, self.end_time,100, "")

class ExecutionHost(models.Model):
	host=models.ForeignKey(Host, related_name="executions")
	run=models.ForeignKey(Run, related_name="executions")
	num_processors=models.IntegerField()

class RunFinishInfo(models.Model):
    run=models.OneToOneField(
                             Run,
                             related_name='runFinishInfo',
                             help_text="The run associated with the accountin info"
                             )
    user_name=models.CharField(
                              max_length=50,
                              verbose_name="User Name", 
                              help_text="User name of the submitter"
                              )
    options=models.IntegerField(
                                verbose_name="Options 1",
                                help_text="Bit flags for job processing"
                                )
    num_processors=models.IntegerField(
                                      verbose_name="Processors Used",
                                      help_text="Number of processors initially requested for execution"
                                      )
    job_status=models.ForeignKey(JobStatus)
    begin_time=models.IntegerField(
                                  verbose_name="Begin Time",
                                  help_text="Job start time - the job should be started at or after this time"
                                  )
    def begin_time_datetime(self):
        return datetime.datetime.utcfromtimestamp(self.begin_time)
    term_time=models.IntegerField(
                                 verbose_name="Termination Deadline",
                                 help_text="Job termination deadline - the job should be terminated by this time"
                                 )
    def term_time_datetime(self):
        return datetime.datetime.utcfromtimestamp(self.term_time)
    requested_resources=models.TextField(
                            verbose_name="Resource Request",
                            help_text="Resource requirement specified by the user"
                            )
    cwd=models.TextField(
                         verbose_name="Curent Working Directory",
                         help_text="Current working directory (up to 4094 characters for UNIX or 255 characters for Windows)"
                         )
    input_file=models.TextField(
                            verbose_name="Input File",
                            help_text="Input file name (up to 4094 characters for UNIX or 255 characters for Windows)"
                            )
    output_file=models.TextField(
                             verbose_name="Output File",
                             help_text="output file name (up to 4094 characters for UNIX or 255 characters for Windows)"
                             )
    error_file=models.TextField(
                             verbose_name="Error File",
                             help_text="Error output file name (up to 4094 characters for UNIX or 255 characters for Windows)"
                             )
    input_file_spool=models.TextField(
                                 verbose_name="Input File Spool",
                                 help_text="Spool input file (up to 4094 characters for UNIX or 255 characters for Windows)"
                                 )
    command_spool=models.TextField(
                                  verbose_name="Command Spool File",
                                  help_text="Spool command file (up to 4094 characters for UNIX or 255 characters for Windows)"
                                  )
    job_file=models.TextField(
                             verbose_name="Job File",
                             help_text="Job script file name"
                             )
    requested_hosts=models.ManyToManyField(Host)
    host_factor=models.FloatField(
                                 verbose_name="Host Factor",
                                 help_text="CPU factor of the first execution host"
                                 )
    job_name=models.TextField(
                             verbose_name="Job Name",
                             help_text="Job name (up to 4094 characters for UNIX or 255 characters for Windows)"
                             )
    command=models.TextField(
                             verbose_name="Command",
                             help_text="Complete batch job command specified by the user (up to 4094 characters for UNIX or 255 characters for Windows)"
                             )
    dependency_conditions=models.TextField(
                                verbose_name="Dependancy Conditions",
                                help_text="Job dependency condition specified by the user"
                                )
    pre_execution_command=models.TextField(
                                verbose_name="Pre Execution Command",
                                help_text="Pre-execution command specified by the user"
                                )
    email_user=models.CharField(
                              max_length=50,
                              verbose_name="Mail User",
                              help_text="Name of the user to whom job related mail was sent"
                              )
    project_name=models.CharField(
                                 max_length=128,
                                 verbose_name="Project Name",
                                 help_text="LSF project name"
                                 )
    exit_reason=models.ForeignKey(ExitReason)                                 
    max_num_processors=models.IntegerField(
                                         verbose_name="Max Processors",
                                         help_text="Maximum number of processors specified for the job"
                                         )
    login_shell=models.CharField(
                                max_length=50,
                                verbose_name="Login Shell",
                                help_text="Login shell used for the job"
                                )
    max_residual_mem=models.IntegerField(
                                verbose_name="Max Residual Memory",
                                help_text="Maximum resident memory usage in KB of all processes in the job"
                                )
    max_swap=models.IntegerField(
                                 verbose_name="Max Swap Usage",
                                 help_text="Maximum virtual memory usage in KB of all processes in the job"
                                 )


class Frob(models.Model):
    utime=models.FloatField(
                            verbose_name="User Time User",
                            help_text="User time used",
                            )
    stime=models.FloatField(
                            verbose_name="System Time Used",
                            help_text="System time used",
                            )

    maxrss=models.FloatField(
                             verbose_name="Max Shared Text Size",
                             help_text="Maximum shared text size",
                             )
    ixrss=models.FloatField(
                            verbose_name="Integral Shared Text Size",
                            help_text="Integral of the shared text size over time (in KB seconds)",
                            )
    ismrss=models.FloatField(
                             verbose_name="Integral Shmem Size",
                             help_text="Integral of the shared memory size over time (valid only on Ultrix)",
                             )
    idrss=models.FloatField(
                            verbose_name="Integral Data Size",
                            help_text="Integral of the unshared data size over time",
                            )
    isrss=models.FloatField(
                            verbose_name="Integral Stack Size",
                            help_text="Integral of the unshared stack size over time",
                            )
    minflt=models.FloatField(
                             verbose_name="Page Reclaims",
                             help_text="Number of page reclaims",
                             )
    majflt=models.FloatField(
                             verbose_name="Page Faults",
                             help_text="Number of page faults",
                             )
    nswap=models.FloatField(
                            verbose_name="Swapped",
                            help_text="Number of times the process was swapped out",
                            )
    inblock=models.FloatField(
                              verbose_name="Blocks Input",
                              help_text="Number of block input operations",
                              )
    oublock=models.FloatField(
                              verbose_name="Blocks Output",
                              help_text="Number of block output operations",
                              )
    ioch=models.FloatField(
                           verbose_name="Characters Read and Written",
                           help_text="Number of characters read and written (valid only on HP-UX)",
                           )
    msgsnd=models.FloatField(
                             verbose_name="Messages Sent",
                             help_text="Number of System V IPC messages sent",)
    msgrcv=models.FloatField(
                             verbose_name="Messages Recieved",
                             help_text="Number of messages received",
                             )
    nsignals=models.FloatField(
                               verbose_name="Signals Received",
                               help_text="Number of signals received",
                               )
    nvcsw=models.FloatField(
                            verbose_name="Voluntary Context Switches",
                            help_text="Number of voluntary context switches",
                            )

    nivcsw=models.FloatField(
                             verbose_name="Involuntary Context Switches",
                             help_text="Number of involuntary context switches",
                             )
    exutime=models.FloatField(
                              verbose_name="Exact User Time",
                              help_text="Exact user time used (valid only on ConvexOS)",
                              )
    def contentionChartN3DS(self):
		data=[{
			'key':"System and User time consumed",
			'values':[
				{
					'label':'System Time',
					'value':self.stime,
				},
				{
					'label':'User Time',
					'value':self.utime,
				},
				],
			},]
		return json.dumps(data)

    def resourceUsageChartN3DS(self):
		data=[{
				'key':"Recorded Resource Usage",
				'values':[
					{
						"label": 'Max RSS',
						"value": self.maxrss,
					},
					{
						"label": 'IX RSS'  ,
						"value":  self.ixrss ,
					},
					{
						"label":'ISM RSS'   ,
						"value":self.ismrss   ,
					},
					{
						"label":'ID RSS'   ,
						"value":self.idrss   ,
					},
					{
						"label": "ISRSS"  ,
						"value": self.isrss  ,
					},
					{
						"label": "MINFLT"  ,
						"value": self.minflt  ,
					},
					{
						"label": "MAJFLT",
						"value": self.majflt,
					},
					{
						"label": "NSWAP",
						"value": self.nswap,
					},
					{
						"label": "INBLOCK",
						"value": self.inblock,
					},
					{
						"label": "OUBLOCK",
						"value": self.oublock,
					},
					{
						"label": "IOCH",
						"value": self.ioch,
					},
					{
						"label": "MSGSND",
						"value": self.msgsnd,
					},
					{
						"label": "NSIGNALS",
						"value": self.nsignals,
					},
					{
						"label": "NVCSW",
						"value": self.nvcsw,
					},
					],
			}]
		return json.dumps(data)

class JobSubmitInfo(models.Model):
	job=models.OneToOneField(Job, related_name='jobSubmitInfo',help_text="The Job Associated with the Event")
	submit_time=models.IntegerField()
	def submit_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.submit_time)
	begin_time=models.IntegerField()
	def begin_timeDT(self):
		return datetime.datetime.utcfromtimestamp(self.begin_time)
	term_time=models.IntegerField()
	def term_timeDT(self):
		return datetime.datetime.utcfromtimestamp(self.begin_time)

	num_processors=models.IntegerField()
	sigValue=models.IntegerField()
	chkpntPeriod=models.IntegerField()
	restartPid=models.IntegerField()
	hostSpec=models.TextField()
	host_factor=models.FloatField()
	umask=models.IntegerField()
	queue=models.ForeignKey(Queue, related_name='jobSubmitInfo')
	requested_resources=models.TextField()
	submit_host=models.ForeignKey(Host, related_name="jobSubmitInfo")
	cwd=models.TextField()
	chkpntDir=models.TextField()
	input_file=models.TextField()
	outFile=models.TextField()
	errFile=models.TextField()
	input_file_spool=models.TextField()
	command_spool=models.TextField()
	jobSpoolDir=models.TextField()
	subHomeDir=models.TextField()
	job_file=models.TextField()
	requested_hosts=models.ManyToManyField(Host)
	dependency_conditions=models.TextField()
	timeEvent=models.TextField()
	job_name=models.TextField()
	command=models.TextField()
	pre_execution_command=models.TextField()
	email_user=models.TextField()
	project=models.ForeignKey(Project)
	schedHostType=models.TextField()
	login_shell=models.TextField()
	userGroup=models.TextField()
	exceptList=models.TextField()
	rsvId=models.TextField()
